import streamlit as st
import pandas as pd
import re
from openai import OpenAI
import json
import logging

# Configuración de logging
logging.basicConfig(level=logging.DEBUG)

# Configuración de la página
st.set_page_config(page_title="Chatbot de Restaurante", page_icon="🍽️")

# Inicialización del cliente OpenAI
client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

# Cargar datos
@st.cache_data
def load_data():
    try:
        menu_df = pd.read_csv('menu.csv')
        cities_df = pd.read_csv('us-cities.csv')
        return menu_df, cities_df['City'].tolist()
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
    
    menu_text = "🍽️ Nuestro Menú:\n\n"
    for category, items in menu_df.groupby('Category'):
        menu_text += f"**{category}**\n"
        for _, item in items.iterrows():
            menu_text += f"• {item['Item']} - {item['Serving Size']} - ${item['Price']:.2f}\n"
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

# Funciones de manejo de entregas
def check_delivery(city):
    if city.lower() in [c.lower() for c in delivery_cities]:
        return f"✅ Sí, realizamos entregas en {city}."
    else:
        return f"❌ Lo siento, actualmente no realizamos entregas en {city}."

def get_delivery_cities():
    return "Realizamos entregas en las siguientes ciudades:\n" + "\n".join(delivery_cities[:10]) + "\n..."

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

def add_to_order(item, quantity):
    logging.debug(f"Añadiendo al pedido: {quantity} x {item}")
    item_lower = item.lower()
    menu_items_lower = [i.lower() for i in menu_df['Item']]
    if item_lower in menu_items_lower:
        index = menu_items_lower.index(item_lower)
        actual_item = menu_df['Item'].iloc[index]
        if actual_item in st.session_state.current_order:
            st.session_state.current_order[actual_item] += quantity
        else:
            st.session_state.current_order[actual_item] = quantity
        total = calculate_total()
        return f"Se ha añadido {quantity} {actual_item}(s) a tu pedido. El total actual es ${total:.2f}"
    else:
        return f"Lo siento, {item} no está en nuestro menú. Por favor, verifica el menú e intenta de nuevo."

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
    order_summary = "Tu pedido actual:\n"
    total = 0
    for item, quantity in st.session_state.current_order.items():
        price = menu_df.loc[menu_df['Item'] == item, 'Price'].iloc[0]
        item_total = price * quantity
        total += item_total
        order_summary += f"• {quantity} x {item} - ${item_total:.2f}\n"
    order_summary += f"\nTotal: ${total:.2f}"
    return order_summary

# Función de filtrado de contenido
def is_inappropriate(text):
    inappropriate_words = ['tonto','tonta']
    return any(word in text.lower() for word in inappropriate_words)

# Función de manejo de consultas
def handle_query(query):
    logging.debug(f"Consulta recibida: {query}")
    if is_inappropriate(query):
        return "Por favor, mantén un lenguaje respetuoso."
    
    query_lower = query.lower()
    
    if "menu" in query_lower or "carta" in query_lower or "menú" in query_lower:
        return get_menu()
    elif re.search(r'\b(entrega|reparto)\b', query_lower):
        city_match = re.search(r'en\s+(\w+)', query_lower)
        if city_match:
            return check_delivery(city_match.group(1))
        else:
            return get_delivery_cities()
    elif re.search(r'\b(pedir|ordenar|pedido)\b', query_lower):
        return start_order()
    elif re.search(r'\b(categoría|categoria)\b', query_lower):
        category_match = re.search(r'(categoría|categoria)\s+(\w+)', query_lower)
        if category_match:
            return get_category_details(category_match.group(2))
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
    elif "modificar pedido" in query_lower:
        item_match = re.search(r'modificar pedido\s+(\d+)\s+(.+)', query_lower)
        if item_match:
            quantity = int(item_match.group(1))
            item = item_match.group(2)
            return modify_order(item, quantity)
        else:
            return "No pude entender qué quieres modificar. Por favor, especifica la cantidad y el item."
    
    # Manejo de pedidos
    order_match = re.findall(r'(\d+)\s*(.*?)(?=\d+\s*|$)', query_lower)
    if order_match:
        response = ""
        for quantity, item in order_match:
            item = item.strip()
            response += add_to_order(item, int(quantity)) + "\n"
        return response.strip()
    
    # Si no se reconoce la consulta, usamos OpenAI para generar una respuesta
    try:
        messages = st.session_state.messages + [{"role": "user", "content": query}]
        response = client.chat.completions.create(
            model="gpt-4-turbo",
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
        return "Lo siento, no pude entender tu consulta. ¿Podrías reformularla?"

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
