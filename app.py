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

# Cargar datos y hacer que los nombres sean insensibles a mayúsculas/minúsculas
@st.cache_data
def load_data():
    try:
        menu_df = pd.read_csv('menu.csv')
        menu_df['Item'] = menu_df['Item'].str.lower()
        menu_df['Item'] = menu_df['Item'].str.replace('[^\x00-\x7F]+', ' ')
        menu_df['Item'] = menu_df['Item'].str.strip()
        menu_df['Category'] = menu_df['Category'].str.lower().str.strip()
        print("Productos disponibles:", menu_df['Item'].unique())
        
        cities_df = pd.read_csv('us-cities.csv')
        cities_df['City'] = cities_df['City'].str.lower().str.strip()
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
        menu_text += f"### {category.title()}\n"
        for _, item in items.iterrows():
            menu_text += f"- **{item['Item'].title()}** - {item['Serving Size']} - ${item['Price']:.2f}\n"
        menu_text += "\n"
    menu_text += "Para ver más detalles de una categoría específica, por favor pregúntame sobre ella."
    return menu_text

# Mejorar la función de manejo de entregas
def check_delivery(city):
    city = city.strip().lower()
    # Permitir que se reconozcan ciudades aunque se escriban con espacios adicionales o ligeras variaciones
    for delivery_city in delivery_cities:
        if city in delivery_city or delivery_city in city:
            return f"✅ Sí, realizamos entregas en {city.title()}."
    return f"❌ Lo siento, actualmente no realizamos entregas en {city.title()}."

# Función de manejo de consultas mejorada para incluir datos del menú y ciudades
def handle_query(query):
    logging.debug(f"Consulta recibida: {query}")

    # Filtro de lenguaje inapropiado
    if is_inappropriate(query):
        return "Por favor, mantén un lenguaje respetuoso."

    # Clasificación de relevancia con GPT, incluyendo datos del menú y ciudades
    try:
        messages = [
            {"role": "system", "content": "Eres un asistente para un restaurante que responde preguntas sobre el menú y entregas."},
            {"role": "user", "content": f"Menú: {get_menu()}\n\nCiudades de entrega: {', '.join([city.title() for city in delivery_cities])}"},
            {"role": "user", "content": query}
        ]
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
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
def show_current_order():
    if not st.session_state.current_order:
        return "No tienes ningún pedido en curso."
    order_summary = "### Tu pedido actual:\n\n"
    total = 0
    for item, quantity in st.session_state.current_order.items():
        price = menu_df.loc[menu_df['Item'] == item.lower(), 'Price'].iloc[0]
        item_total = price * quantity
        total += item_total
        order_summary += f"- **{quantity} x {item.title()}** - ${item_total:.2f}\n"
    order_summary += f"\n**Total:** ${total:.2f}"
    return order_summary

if st.session_state.current_order:
    st.sidebar.markdown("## Pedido Actual")
    st.sidebar.markdown(show_current_order())
    if st.sidebar.button("Confirmar Pedido"):
        st.sidebar.markdown(confirm_order())
    if st.sidebar.button("Cancelar Pedido"):
        st.sidebar.markdown(cancel_order())

logging.debug(f"Estado del pedido actual: {st.session_state.current_order}")
