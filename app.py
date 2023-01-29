from flask import Flask, render_template, request, flash, abort, redirect, url_for
from flask_caching import Cache
import openai
from prestapyt import PrestaShopWebServiceDict
from PIL import Image
import deepl
import os
import io
import urllib.request

config = {
    "DEBUG": True,          # some Flask specific configs
    "CACHE_TYPE": "SimpleCache",  # Flask-Caching related configs
    "CACHE_DEFAULT_TIMEOUT": 900
}

app = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)
app.secret_key = "ksdhgfhj32498pfa-30ru2ß0239ur5"

credentials = {
    "OpenAI": os.environ.get("OPENAI"),  # max 5 $/month
    "DeepL": os.environ.get("DEEPL"),  # max 500.000 characters/month, but free
    "PrestaShop": os.environ.get("PRESTA")
}
prestashop = PrestaShopWebServiceDict('http://3.91.148.17/api', credentials["PrestaShop"])
prestashop.debug = True

openai.api_key = credentials["OpenAI"]

def translate(text, target_lang="DE"):
    translator = deepl.Translator(auth_key=credentials["DeepL"])
    return translator.translate_text(text, target_lang=target_lang)

def check_product(p_id):
    try:
        product = prestashop.get(f"products/{p_id}")  # /?display=[name,manufacturer_name,id_supplier,type,price,description]")
        return product
    except:
        return None

@cache.memoize(timeout=900)
def generate_images(prompt):
    prompt_en = translate(prompt, target_lang="EN-US")
    response = openai.Image.create(
        prompt=str(prompt_en),
        n=8,
        size="1024x1024",
        response_format="url"
    )
    return [r["url"] for r in response["data"]]

@cache.memoize(timeout=900)
def get_description(product):
    def get_attributes():
        features_out = ""

        features = product.get('product', {}).get('associations', {}).get('product_features', {}).get('product_feature')
        features = [features] if isinstance(features, dict) else features
        # {'id': '1', 'id_feature_value': '3'}
        # [{'id': '3', 'id_feature_value': '12'}, {'id': '5', 'id_feature_value': '21'}, {'id': '7', 'id_feature_value': '28'}]
        ex_feature = []
        for key in features:
            # Extrahieren vom Namen des Produktfeatures
            temp = key.get('id')
            p_Feature_name = prestashop.get(f"product_features/{temp}")
            Feature_name = p_Feature_name.get('product_feature', {}).get('name', {}).get('language', {})
            h1 = Feature_name[0]
            h2 = h1.get('value')

            # Extrahieren vom dazugehörigenden Feature Value
            temp1 = key.get('id_feature_value')
            p_Feature_value = prestashop.get(f"product_feature_values/{temp1}")
            Feature_value = p_Feature_value.get('product_feature_value', {}).get('value', {}).get('language', {})
            i1 = Feature_value[0]
            i2 = i1.get('value')

            output = [h2 + ':', i2]
            ex_feature.extend(output)

        counter = 0
        # Aufbereitung der Feature Liste für die Promt
        for f in range(0, len(ex_feature)):
            counter += 1
            features_out += f"{ex_feature[f]}"
            if counter > 1:
                features_out += "\n"
                counter = 0

        manufacturer_name = product["product"]["manufacturer_name"]["value"]

        type_ = product["product"]["type"]["value"]
        price = product["product"]["price"]
        name = product["product"]["name"]["language"][0]["value"]  # language 0 is EN

        if manufacturer_name == "":
            return f"price: {price}, name: {name}"
        else:
            return f"manufacturer: {manufacturer_name}, price: {price}, name: {name}"

    def generate_description(attr, features_out=""):
        # product_attributes = "type:Radio\ncolor:red\nwatt:2000W\nprice:1200$\n"
        prompt = f"""Write a product description of at least 100 words based on the following attributes: \n {attr} and Features: \n {features_out}
        Also state the facts to inform the customer, but don't overdo it and do not exaggerate with the product description. """
        print(f"Prompt: {prompt}")

        # Bitte nicht in Dauerschleife laufen lassen, sonst erreichen wir das usage limit ._.
        response = openai.Completion.create(
            model="text-davinci-003",
            prompt=prompt,
            temperature=0.7,
            max_tokens=128,  # 512 = 1 ct per request
            top_p=1,
            frequency_penalty=0,
            presence_penalty=0
        )

        response_text = response["choices"][0]["text"]
        return response_text

    attributes = get_attributes()
    desc_en = generate_description(attributes)
    desc_de = translate(desc_en)
    return str(desc_de).strip()


@app.route("/", methods=["GET", "POST"])
def beschreibung():
    if request.method == "POST":
        final_desc = request.form.get("beschreibung")
        if final_desc:
            # flash("Produkt aktualisiert", "success")
            return render_template("beschreibung.html")

        p_id = request.form.get("produkt")
        product = check_product(p_id)

        if not product:
            flash(f"Es konnte kein Produkt mit der ID {p_id} gefunden werden.", "danger")
            return render_template("beschreibung.html")

        try:
            desc = get_description(product)
        except openai.error.ServiceUnavailableError:
            abort(500)
        flash("Die folgende Beschreibung wurde automatisch generiert. Du kannst hier noch änderungen vornehmen, und sie dann in den Shop kopieren..", "success")
        return render_template("beschreibung.html", desc=desc)

    return render_template("beschreibung.html")

@app.route("/bilder", methods=["GET", "POST"])
def bilder():
    if request.method == "POST":
        url = request.form.get("img")
        if url:
            img_filename = "temp_img.png"
            urllib.request.urlretrieve(url, img_filename)

            img = Image.open(img_filename)
            img.convert("RGB").save("temp_img.jpg")

            with io.open("temp_img.jpg", "rb") as f:
                content = f.read()

            prestashop.add(f"/images/products/{request.form.get('produkt')}", files=[("image", "temp_img.jpg", content)])
            flash(f"Das Bild wurde erfolgreich zum Produkt hinzugefügt!", "success")
            return redirect(url_for("bilder"))

        p_id = request.form.get("produkt")
        product = check_product(p_id)
        if not product:
            flash(f"Es konnte kein Produkt mit der ID {p_id} gefunden werden.", "danger")
            return render_template("bilder.html")

        prompt = request.form.get("prompt")
        urls = generate_images(prompt)
        flash(f"Die folgenden Bilder wurden automatisch generiert. Wähle das aus, was für das Produkt mit der ID {p_id} hochgeladen werden soll.", "success")
        return render_template("bilder.html", urls=urls, p_id=p_id)
    return render_template("bilder.html")
