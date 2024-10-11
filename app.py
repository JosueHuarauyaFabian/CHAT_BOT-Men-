import streamlit as st
import pandas as pd
import re
from openai import OpenAI
import json
import logging
import inflect

# Configuración de logging
logging.basicConfig(level=logging.DEBUG)

# Configuración de la página
st.set_page_config(page_title="Chatbot de Restaurante", page_icon="🍽️")

# Inicialización del cliente OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Cargar datos y hacer que los nombres sean insensibles a mayúsculas/minúsculas
@st.cache_data
def load_data():
    try:
        menu_df = pd.read_csv('menu.csv')
        menu_df['Item'] = menu_df['Item'].str.lower()
        menu_df['Item'] = menu_df['Item'].str.replace('[^\x00-\x7F]+', ' ')
        menu_df['Item'] = menu_df['Item'].str.strip()
        print("Productos disponibles:", menu_df['Item'].unique())
        
        cities_df = pd.read_csv('us-cities.csv')
        delivery_cities = cities_df['City'].tolist()
        
        # Imprimir el contenido de delivery_cities para depurar
        print("Contenido de delivery_cities:", delivery_cities)
        print("Tipos de elementos en delivery_cities:", [type(city) for city in delivery_cities])
        
        return menu_df, delivery_cities
    except Exception as e:
        logging.error(f"Error al cargar los datos: {e}")
        return pd.DataFrame(), []

menu_df, delivery_cities = load_data()

if menu_df.empty:
    st.error("No se pudo cargar el menú. Por favor, verifica el archivo menu.csv.")
else:
    logging.info(f"Menú cargado correctamente. Categorías: {', '.join(menu_df['Category'].unique())}")
    logging.debug(f"Primeras filas del menú:\n{menu_df.head()}")

# Funciones de manejo del menú
def get_menu():
    logging.debug("Función get_menu() llamada")
    if menu_df.empty:
        return "Lo siento, no pude cargar el menú. Por favor, contacta al soporte técnico."
    
    menu_text = "🍽️ **Nuestro Menú:**\n\n"
    for category, items in menu_df.groupby('Category'):
        menu_text += f"### {category}\n"
        for _, item in items.iterrows():
            menu_text += f"- **{item['Item']}** - {item['Serving Size']} - ${item['Price']:.2f}\n"
        menu_text += "\n"
    menu_text += "Para ver más detalles de una categoría específica, por favor pregúntame sobre ella."
    return menu_text

def get_category_details(category):
    logging.debug(f"Detalles solicitados para la categoría: {category}")
    category_items = menu_df[menu_df['Category'] == category]
    if category_items.empty:
        return f"Lo siento, no encontré información sobre la categoría '{category}'."
    
    details = f"Detalles de {category}:\n\n"
    for _, item in category_items.iterrows():
        details += f"• {item['Item']} - {item['Serving Size']} - ${item['Price']:.2f}\n"
    return details

# Funciones de manejo de entregas (coloca estas funciones después de las funciones del menú)
def check_delivery(city):
    if city.lower() in [c.lower() for c in delivery_cities]:
        return f"✅ Sí, realizamos entregas en {city}."
    else:
        return f"❌ Lo siento, actualmente no realizamos entregas en {city}."

def get_delivery_cities():
    # Asegurarse de que delivery_cities sea una lista de cadenas
    if all(isinstance(city, str) for city in delivery_cities):
        return "Realizamos entregas en las siguientes ciudades:\n" + "\n".join(delivery_cities) + "\n..."
    else:
        logging.error("La lista de ciudades de entrega contiene datos no válidos.")
        return "Lo siento, hubo un problema al cargar las ciudades de entrega."
    
# Funciones de manejo de pedidos
def calculate_total():
    total = 0
    for item, quantity in st.session_state.current_order.items():
        price = menu_df.loc[menu_df['Item'].str.lower() == item.lower(), 'Price']
        if not price.empty:
            total += price.iloc[0] * quantity
        else:
            logging.warning(f"No se encontró el precio para {item}.")
    return total

def get_category(item_name):
    # Buscar el producto en el DataFrame y retornar su categoría
    item_row = menu_df[menu_df['Item'].str.lower() == item_name.lower()]
    if not item_row.empty:
        return item_row['Category'].iloc[0]
    else:
        return None  # Devuelve None si el producto no se encuentra

# Inicializar inflect para manejar singulares y plurales
p = inflect.engine()

def add_to_order(item, quantity):
    logging.debug(f"Añadiendo al pedido: {quantity} x {item}")
    
    # Limitar la cantidad máxima que se puede pedir de un solo producto
    if quantity > 100:
        return f"Lo siento, no puedes pedir más de 100 unidades de {item}."

    # Normalizar el nombre del producto ingresado por el usuario
    item_lower = item.strip().lower()
    singular_item = p.singular_noun(item_lower) or item_lower  # Convertir a singular si es plural
    menu_items_lower = [i.strip().lower() for i in menu_df['Item']]
    
    # Intentar una búsqueda exacta primero
    if singular_item in menu_items_lower:
        index = menu_items_lower.index(singular_item)
        actual_item = menu_df['Item'].iloc[index]
    else:
        # Si no se encuentra una coincidencia exacta, realizar una búsqueda parcial
        matching_items = menu_df[menu_df['Item'].str.contains(singular_item, case=False)]
        if not matching_items.empty:
            actual_item = matching_items.iloc[0]['Item']
        else:
            return f"Lo siento, '{item}' no está en nuestro menú. Por favor, verifica el menú e intenta de nuevo."

    # Verificar la categoría del producto para asegurar que sea válida
    category = get_category(actual_item)
    if category and category.lower() not in permitted_categories:
        return "Lo siento, solo vendemos productos de las categorías disponibles en nuestro menú. ¿Te gustaría ver nuestro menú?"

    # Añadir el producto encontrado al pedido
    if actual_item in st.session_state.current_order:
        st.session_state.current_order[actual_item] += quantity
    else:
        st.session_state.current_order[actual_item] = quantity

    # Calcular el subtotal para el artículo recién agregado
    item_price = menu_df.loc[menu_df['Item'].str.lower() == actual_item.lower(), 'Price'].iloc[0]
    item_total = item_price * quantity

    # Generar el desglose de los artículos
    response = f"Has añadido {quantity} {actual_item}(s) a tu pedido. Subtotal para este artículo: ${item_total:.2f}.\n\n"
    
    # Mostrar el desglose del pedido completo
    response += "### Resumen de tu pedido actual:\n"
    order_total = 0
    for order_item, order_quantity in st.session_state.current_order.items():
        order_item_price = menu_df.loc[menu_df['Item'].str.lower() == order_item.lower(), 'Price'].iloc[0]
        order_item_total = order_item_price * order_quantity
        order_total += order_item_total
        response += f"- {order_quantity} x {order_item} - Subtotal: ${order_item_total:.2f}\n"
    
    response += f"\n**Total acumulado del pedido:** ${order_total:.2f}"
    
    return response

def remove_from_order(item):
    logging.debug(f"Eliminando del pedido: {item}")
    item_lower = item.lower()
    for key in list(st.session_state.current_order.keys()):
        if key.lower() == item_lower:
            del st.session_state.current_order[key]
            total = calculate_total()
            return f"Se ha eliminado {key} de tu pedido. El total actual es ${total:.2f}"
    return f"{item} no estaba en tu pedido."

def modify_order(item, quantity):
    logging.debug(f"Modificando pedido: {quantity} x {item}")
    item_lower = item.lower()
    for key in list(st.session_state.current_order.keys()):
        if key.lower() == item_lower:
            if quantity > 0:
                st.session_state.current_order[key] = quantity
                total = calculate_total()
                return f"Se ha actualizado la cantidad de {key} a {quantity}. El total actual es ${total:.2f}"
            else:
                del st.session_state.current_order[key]
                total = calculate_total()
                return f"Se ha eliminado {key} del pedido. El total actual es ${total:.2f}"
    return f"{item} no está en tu pedido actual."

def start_order():
    return ("Para realizar un pedido, por favor sigue estos pasos:\n"
            "1. Revisa nuestro menú\n"
            "2. Dime qué items te gustaría ordenar\n"
            "3. Proporciona tu dirección de entrega\n"
            "4. Confirma tu pedido\n\n"
            "¿Qué te gustaría ordenar?")

def save_order_to_json(order):
    with open('orders.json', 'a') as f:
        json.dump(order, f)
        f.write('\n')

def confirm_order():
    if not st.session_state.current_order:
        return "No hay ningún pedido para confirmar. ¿Quieres empezar uno nuevo?"
    
    order_df = pd.DataFrame(list(st.session_state.current_order.items()), columns=['Item', 'Quantity'])
    order_df['Total'] = order_df.apply(lambda row: menu_df.loc[menu_df['Item'] == row['Item'], 'Price'].iloc[0] * row['Quantity'], axis=1)
    
    # Guardar en CSV
    order_df.to_csv('orders.csv', mode='a', header=False, index=False)
    
    # Guardar en JSON
    order_json = {
        'items': st.session_state.current_order,
        'total': calculate_total()
    }
    save_order_to_json(order_json)
    
    total = calculate_total()
    st.session_state.current_order = {}
    return f"¡Gracias por tu pedido! Ha sido confirmado y guardado en CSV y JSON. El total es ${total:.2f}"

def cancel_order():
    if not st.session_state.current_order:
        return "No hay ningún pedido para cancelar."
    st.session_state.current_order = {}
    return "Tu pedido ha sido cancelado."

def show_current_order():
    if not st.session_state.current_order:
        return "No tienes ningún pedido en curso."
    order_summary = "### Tu pedido actual:\n\n"
    total = 0
    for item, quantity in st.session_state.current_order.items():
        price = menu_df.loc[menu_df['Item'] == item, 'Price'].iloc[0]
        item_total = price * quantity
        total += item_total
        order_summary += f"- **{quantity} x {item}** - ${item_total:.2f}\n"
    order_summary += f"\n**Total:** ${total:.2f}"
    return order_summary

# Función de filtrado de contenido
def is_inappropriate(text):
    # Utilizar GPT para verificar si el contenido es inapropiado
    try:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "¿Este texto contiene lenguaje inapropiado o ofensivo? Responde solo 'sí' o 'no'."},
                {"role": "user", "content": text}
            ],
            max_tokens=2,  # Limitamos a solo "sí" o "no"
            temperature=0.0,
        )
        
        # Procesar la respuesta de GPT
        response_content = response.choices[0].message.content.strip().lower()
        return response_content == 'sí'
    except Exception as e:
        logging.error(f"Error al verificar el lenguaje inapropiado con GPT: {e}")
        # Como medida de seguridad, consideramos cualquier error como potencialmente inapropiado
        return False

# Función de manejo de consultas
def handle_query(query):
    logging.debug(f"Consulta recibida: {query}")

    # Filtro de lenguaje inapropiado
    if is_inappropriate(query):
        return "Por favor, mantén un lenguaje respetuoso."

    # Clasificación de relevancia con GPT
    try:
        relevance_check = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "¿Está esta consulta relacionada con un restaurante o su menú? Responde con 'sí' o 'no'."},
                {"role": "user", "content": query}
            ],
            max_tokens=2,
            temperature=0.0,
        )
        relevance_response = relevance_check.choices[0].message.content.strip().lower()
        if relevance_response == 'no':
            return ("Lo siento, solo puedo ayudarte con temas relacionados al restaurante. "
                    "¿Te gustaría saber más sobre nuestro menú o realizar un pedido?")
    except Exception as e:
        logging.error(f"Error al verificar la relevancia con GPT: {e}")
        return ("Lo siento, no pude procesar tu consulta. Inténtalo nuevamente o pregunta algo "
                "relacionado con el restaurante.")

    query_lower = query.lower()
    order_match = re.findall(r'(\d+)\s+(.*?)\s*(?:y|,|\.|$)', query_lower)
    if order_match:
        response = ""
        for quantity, item in order_match:
            item = item.strip()
            response += add_to_order(item, int(quantity)) + "\n"
        return response.strip()
    
    if "menu" in query_lower or "carta" in query_lower or "menú" in query_lower:
        return get_menu()
    elif "ciudades" in query_lower and ("entrega" in query_lower or "reparte" in query_lower):
        return get_delivery_cities()
    elif re.search(r'\b(entrega|reparto)\b', query_lower):
        city_match = re.search(r'en\s+(\w+)', query_lower)
        if city_match:
            return check_delivery(city_match.group(1))
        else:
            return get_delivery_cities()
    elif re.search(r'\b(precio|costo)\b', query_lower):
        item_match = re.search(r'(precio|costo)\s+de\s+(.+)', query_lower)
        if item_match:
            item = item_match.group(2)
            price = menu_df.loc[menu_df['Item'].str.lower() == item.lower(), 'Price']
            if not price.empty:
                return f"El precio de {item} es ${price.iloc[0]:.2f}"
            else:
                return f"Lo siento, no encontré el precio de {item}."
    elif "mostrar pedido" in query_lower:
        return show_current_order()
    elif "cancelar pedido" in query_lower:
        return cancel_order()
    elif "confirmar pedido" in query_lower:
        return confirm_order()

    try:
        messages = st.session_state.messages + [{"role": "user", "content": query}]
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": m["role"], "content": m["content"]}
                for m in messages
            ],
            max_tokens=150,
            temperature=0.7,
        )
        return response.choices[0].message.content
    except Exception as e:
        logging.error(f"Error generating response with OpenAI: {e}")
        return ("Lo siento, no pude entender tu consulta. ¿Podrías reformularla con algo "
                "relacionado con nuestro restaurante?")


# Título de la aplicación
st.title("🍽️ Chatbot de Restaurante")

# Inicialización del historial de chat y pedido actual en la sesión de Streamlit
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "¡Hola! Bienvenido a nuestro restaurante. ¿En qué puedo ayudarte hoy? Si quieres ver nuestro menú, solo pídemelo."}
    ]
if "current_order" not in st.session_state:
    st.session_state.current_order = {}

# Mostrar mensajes existentes
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Campo de entrada para el usuario
if prompt := st.chat_input("¿En qué puedo ayudarte hoy?"):
    # Agregar mensaje del usuario al historial
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # Mostrar el mensaje del usuario
    with st.chat_message("user"):
        st.markdown(prompt)
    
    # Generar respuesta del chatbot
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        full_response = handle_query(prompt)
        message_placeholder.markdown(full_response)
    
    # Agregar respuesta del chatbot al historial
    st.session_state.messages.append({"role": "assistant", "content": full_response})

# Mostrar el pedido actual
if st.session_state.current_order:
    st.sidebar.markdown("## Pedido Actual")
    st.sidebar.markdown(show_current_order())
    if st.sidebar.button("Confirmar Pedido"):
        st.sidebar.markdown(confirm_order())
    if st.sidebar.button("Cancelar Pedido"):
        st.sidebar.markdown(cancel_order())

logging.debug(f"Estado del pedido actual: {st.session_state.current_order}")
