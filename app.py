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

# Inicialización del cliente OpenAI con manejo de errores
try:
    client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])
except Exception as e:
    logging.error(f"Error al inicializar el cliente OpenAI: {e}")
    st.error("No se pudo conectar con el servicio de OpenAI. Verifica la configuración de la API.")

# Cargar datos y hacer que los nombres sean insensibles a mayúsculas/minúsculas
@st.cache_data(ttl=3600)
def load_data():
    try:
        menu_df = pd.read_csv('menu.csv')
        menu_df['Item'] = menu_df['Item'].str.lower()
        menu_df['Item'] = menu_df['Item'].str.replace('[^\x00-\x7F]+', ' ')
        menu_df['Item'] = menu_df['Item'].str.strip()
        menu_df['Category'] = menu_df['Category'].str.lower().str.strip()
        print("Productos disponibles:", menu_df['Item'].unique())
        
        cities_df = pd.read_csv('us-cities.csv')
        delivery_cities = cities_df['City'].str.lower().tolist()
        
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

def get_category_details(category):
    logging.debug(f"Detalles solicitados para la categoría: {category}")
    category = category.lower().strip()
    category_items = menu_df[menu_df['Category'] == category]
    if category_items.empty:
        return f"Lo siento, no encontré información sobre la categoría '{category}'."
    
    details = f"Detalles de {category.title()}:\n\n"
    for _, item in category_items.iterrows():
        details += f"• {item['Item'].title()} - {item['Serving Size']} - ${item['Price']:.2f}\n"
    return details

# Funciones de manejo de entregas (coloca estas funciones después de las funciones del menú)
def check_delivery(city):
    city = city.strip().lower()
    if city in delivery_cities:
        return f"✅ Sí, realizamos entregas en {city.title()}. ¿Te gustaría continuar con tu pedido?"
    else:
        return f"❌ Lo siento, actualmente no realizamos entregas en {city.title()}."

def get_delivery_cities():
    if all(isinstance(city, str) for city in delivery_cities):
        cities_list = '\n'.join([city.title() for city in delivery_cities])
        return f"Realizamos entregas en las siguientes ciudades:\n\n{cities_list}"
    else:
        logging.error("La lista de ciudades de entrega contiene datos no válidos.")
        return "Lo siento, hubo un problema al cargar las ciudades de entrega."
    
# Funciones de manejo de pedidos
def calculate_total():
    total = 0
    for item, quantity in st.session_state.current_order.items():
        price = menu_df.loc[menu_df['Item'] == item, 'Price']
        if not price.empty:
            total += price.iloc[0] * quantity
        else:
            logging.warning(f"No se encontró el precio para {item}.")
    return total

def get_category(item_name):
    # Buscar el producto en el DataFrame y retornar su categoría
    item_name = item_name.lower().strip()
    item_row = menu_df[menu_df['Item'] == item_name]
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

    # Lista de categorías permitidas
    permitted_categories = [
        'beverages', 'breakfast', 'chicken & fish', 'coffee & tea', 
        'desserts', 'salads', 'smoothies & shakes', 'snacks & sides'
    ]

    # Normalizar el nombre del producto ingresado por el usuario
    item_lower = item.strip().lower()
    singular_item = p.singular_noun(item_lower) or item_lower
    menu_items_lower = [i.strip().lower() for i in menu_df['Item']]
    
    # Intentar una búsqueda exacta primero
    if singular_item in menu_items_lower:
        index = menu_items_lower.index(singular_item)
        actual_item = menu_df['Item'].iloc[index]
    else:
        similar_items = menu_df[menu_df['Item'].str.contains(re.escape(singular_item[:3]), case=False)]  # Buscar por las primeras letras
        if not similar_items.empty:
            suggestions = ', '.join(similar_items['Item'].unique()[:3])
            return f"Lo siento, '{item}' no está en nuestro menú. ¿Quizás quisiste decir uno de estos? {suggestions}."
        return f"Lo siento, '{item}' no está en nuestro menú. Por favor, verifica el menú e intenta de nuevo."

    # Verificar la categoría del producto para asegurar que sea válida
    category = get_category(actual_item)
    if category and category.lower() not in permitted_categories:
        return "Lo siento, solo vendemos productos de las categorías disponibles en nuestro menú. ¿Te gustaría ver nuestro menú?"

    # Añadir el producto encontrado al pedido
    st.session_state.current_order[actual_item] = st.session_state.current_order.get(actual_item, 0) + quantity

    # Calcular el subtotal para el artículo recién agregado
    item_price = menu_df.loc[menu_df['Item'] == actual_item, 'Price'].iloc[0]
    item_total = item_price * quantity

    # Generar el desglose de los artículos
    response = f"Has añadido {quantity} {actual_item.title()}(s) a tu pedido. Subtotal para este artículo: ${item_total:.2f}.\n\n"
    
    # Mostrar el desglose del pedido completo
    response += "### Resumen de tu pedido actual:\n"
    order_total = 0
    for order_item, order_quantity in st.session_state.current_order.items():
        order_item_price = menu_df.loc[menu_df['Item'] == order_item, 'Price'].iloc[0]
        order_item_total = order_item_price * order_quantity
        order_total += order_item_total
        response += f"- {order_quantity} x {order_item.title()} - Subtotal: ${order_item_total:.2f}\n"
    
    response += f"\n**Total acumulado del pedido:** ${order_total:.2f}"
    
    update_sidebar()  # Asegurar que el sidebar se actualice después de cada cambio
    return response

def remove_from_order(item):
    logging.debug(f"Eliminando del pedido: {item}")
    item_lower = item.lower()
    for key in list(st.session_state.current_order.keys()):
        if key.lower() == item_lower:
            del st.session_state.current_order[key]
            total = calculate_total()
            update_sidebar()
            return f"Se ha eliminado {key.title()} de tu pedido. El total actual es ${total:.2f}"
    return f"{item.title()} no estaba en tu pedido."
    
def modify_order(item, quantity):
    logging.debug(f"Modificando pedido: {quantity} x {item}")
    item_lower = item.lower()
    for key in list(st.session_state.current_order.keys()):
        if key.lower() == item_lower:
            if quantity > 0:
                st.session_state.current_order[key] = quantity
            else:
                del st.session_state.current_order[key]
            update_sidebar()
            return f"Se ha actualizado la cantidad de {key.title()} a {quantity}. El total actual es ${calculate_total():.2f}"
    return f"{item.title()} no está en tu pedido actual."

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
    update_sidebar()
    return f"¡Gracias por tu pedido! Ha sido confirmado y guardado en CSV y JSON. El total es ${total:.2f}"

def cancel_order():
    if not st.session_state.current_order:
        return "No hay ningún pedido para cancelar."
    st.session_state.current_order = {}
    update_sidebar()
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
        order_summary += f"- **{quantity} x {item.title()}** - ${item_total:.2f}\n"
    order_summary += f"\n**Total:** ${total:.2f}"
    return order_summary

# Función para mostrar el pedido actual en el sidebar
def update_sidebar():
    st.sidebar.markdown("## Pedido Actual")
    st.sidebar.markdown(show_current_order())
    if st.sidebar.button("Confirmar Pedido"):
        st.sidebar.markdown(confirm_order())
        st.experimental_rerun()  # Recarga para actualizar la aplicación
    if st.sidebar.button("Cancelar Pedido"):
        st.sidebar.markdown(cancel_order())
        st.experimental_rerun()  # Recarga para actualizar la aplicación

# Llama a la función de actualización del sidebar
update_sidebar()

logging.debug(f"Estado del pedido actual: {st.session_state.current_order}")
