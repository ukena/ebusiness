from flask import Flask, render_template, request, flash
import openai
from prestapyt import PrestaShopWebServiceDict
import deepl
import os

app = Flask(__name__)
app.secret_key = "ksdhgfhj32498pfa-30ru2ß0239ur5"

credentials = {
    "OpenAI": os.environ.get("OPENAI"),  # max 5 $/month
    "DeepL": os.environ.get("DEEPL"),  # max 500.000 characters/month, but free
    "PrestaShop": os.environ.get("PRESTA")
}
prestashop = PrestaShopWebServiceDict('http://3.91.148.17/api', credentials["PrestaShop"])
prestashop.debug = True

def check_product(p_id):
    try:
        product = prestashop.get(f"products/{p_id}/?display=[name,manufacturer_name,id_supplier,type,price,description]")
        return product
    except:
        return None

def get_description(product):
    def get_attributes():
        manufacturer_name = product["product"]["manufacturer_name"]["value"]
        type_ = product["product"]["type"]["value"]
        price = product["product"]["price"]
        name = product["product"]["name"]["language"][0]["value"]  # language 0 is EN
        # product_features = product["product"]["associations"]["product_features"]["product_feature"]

        product_attributes = {
            "manufacturer_name": manufacturer_name,
            "type": type_,
            "price in €": price,
            "name": name,
        }
        product_attribute_str = ""

        for k, v in product_attributes.items():
            product_attribute_str = f"{k}: {v}, "

        product_attribute_str = product_attribute_str[:-2]
        return product_attribute_str

    def generate_description(attributes):
        # open ai anfragen, um eine description zu erzeugen
        openai.api_key = credentials["OpenAI"]

        # product_attributes = "type:Radio\ncolor:red\nwatt:2000W\nprice:1200$\n"
        prompt = f"""Write a product description of at least 100 words based on the following attributes: {attributes}\n 
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
        # vH)~@Zb]UWx7L9eE
        # print(response)
        response_text = response["choices"][0]["text"]
        return response_text

    def translate(text):
        translator = deepl.Translator(auth_key=credentials["DeepL"])
        return translator.translate_text(text, target_lang="DE")

    attributes = get_attributes()
    desc_en = generate_description(attributes)
    desc_de = translate(desc_en)
    return str(desc_de).strip()


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        final_desc = request.form.get("beschreibung")
        if final_desc:
            # TODO: handle produkt update
            flash("Produkt aktualisiert", "success")
            return render_template("index.html")

        p_id = request.form.get("produkt")
        product = check_product(p_id)

        if not product:
            flash(f"Es konnte kein Produkt mit der ID {p_id} gefunden werden.", "danger")
            return render_template("index.html")

        desc = get_description(product)
        flash("Die folgende Beschreibung wurde automatisch generiert. Gern kannst Du noch finale Änderungen vornehmen, bevor die Beschreibung aktualisiert wird.", "success")
        return render_template("index.html", desc=desc)

    return render_template("index.html")
