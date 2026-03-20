from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from datetime import datetime

app = Flask(__name__)
CORS(app)

# -------------------------------
# DATABASE CONFIG
# -------------------------------
DB_CONFIG = {
    "host": "localhost",
    "database": "restaurant_db",
    "user": "root",
    "password": "1234"
}


def get_db_connection():
    """Создание подключения к базе"""
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        print(f"DB connection error: {e}")
        return None


# -------------------------------
# MAIN PAGE
# -------------------------------
@app.route("/")
def index():
    return render_template("index.html")


# -------------------------------
# AUTHORIZATION
# -------------------------------
@app.route("/api/login", methods=["POST"])
def login():
    data = request.json

    username = data.get("username")
    password = data.get("password")

    # Вход как гость
    if username == "guest":
        return jsonify({
            "message": "Вход выполнен",
            "user": {
                "id": 0,
                "username": "Гость",
                "role": "гость"
            }
        })

    conn = get_db_connection()
    if not conn:
        return jsonify({"message": "Ошибка БД"}), 500

    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT id, username, role FROM users WHERE username=%s AND password=%s",
        (username, password)
    )

    user = cursor.fetchone()

    conn.close()

    if user:
        return jsonify({"message": "Вход выполнен", "user": user})

    return jsonify({"message": "Неверные данные"}), 401


# -------------------------------
# STATISTICS
# -------------------------------
@app.route("/api/stats", methods=["GET"])
def get_stats():

    conn = get_db_connection()
    if not conn:
        return jsonify({}), 500

    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM tables WHERE status='свободен'")
    free_tables = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM tables WHERE status='занят'")
    busy_tables = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(*) FROM reservations WHERE DATE(reservation_datetime)=CURDATE()"
    )
    today_reservations = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM orders WHERE status='открыт'")
    active_orders = cursor.fetchone()[0]

    conn.close()

    return jsonify({
        "free_tables": free_tables,
        "busy_tables": busy_tables,
        "today_reservations": today_reservations,
        "active_orders": active_orders
    })


# -------------------------------
# TABLES
# -------------------------------
@app.route("/api/tables", methods=["GET"])
def get_tables():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM tables")
    tables = cursor.fetchall()

    conn.close()

    return jsonify(tables)


@app.route("/api/tables/<int:table_id>", methods=["PUT"])
def update_table(table_id):

    status = request.json.get("status")

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE tables SET status=%s WHERE id=%s",
        (status, table_id)
    )

    conn.commit()
    conn.close()

    return jsonify({"message": "Статус обновлен"})


# -------------------------------
# RESERVATIONS
# -------------------------------
@app.route("/api/reservations", methods=["GET", "POST"])
def reservations():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Получить все брони
    if request.method == "GET":

        query = """
        SELECT r.id,
               r.client_name,
               r.client_phone,
               r.reservation_datetime,
               t.table_number
        FROM reservations r
        JOIN tables t ON r.table_id = t.id
        ORDER BY r.reservation_datetime
        """

        cursor.execute(query)

        reservations = cursor.fetchall()

        for r in reservations:
            if r["reservation_datetime"]:
                r["reservation_datetime"] = r["reservation_datetime"].strftime("%Y-%m-%d %H:%M")

        conn.close()

        return jsonify(reservations)

    # Создать бронь
    if request.method == "POST":

        data = request.json
        user_id = data.get("user_id") if data.get("user_id") != 0 else None

        try:

            cursor.execute(
                """
                INSERT INTO reservations
                (client_name, client_phone, reservation_datetime, table_id, created_by)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (
                    data["client_name"],
                    data["client_phone"],
                    data["datetime"],
                    data["table_id"],
                    user_id
                )
            )

            cursor.execute(
                "UPDATE tables SET status='занят' WHERE id=%s",
                (data["table_id"],)
            )

            conn.commit()

            return jsonify({"message": "Бронь создана"}), 201

        except Error as e:

            conn.rollback()
            return jsonify({"message": str(e)}), 500

        finally:
            conn.close()


@app.route("/api/reservations/<int:reservation_id>", methods=["DELETE"])
def delete_reservation(reservation_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM reservations WHERE id=%s",
        (reservation_id,)
    )

    conn.commit()
    conn.close()

    return jsonify({"message": "Бронь удалена"})


# -------------------------------
# MENU
# -------------------------------
@app.route("/api/menu", methods=["GET", "POST"])
def menu():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Получить меню
    if request.method == "GET":

        query = """
        SELECT m.*,
               IFNULL(ROUND(AVG(r.rating),1),0) AS avg_rating,
               COUNT(r.id) AS review_count
        FROM menu m
        LEFT JOIN reviews r ON m.id = r.dish_id
        GROUP BY m.id
        ORDER BY m.category, m.name
        """

        cursor.execute(query)

        menu = cursor.fetchall()

        conn.close()

        return jsonify(menu)

    # Добавить блюдо
    if request.method == "POST":

        data = request.json

        try:

            cursor.execute(
                "INSERT INTO menu (name,price,category) VALUES (%s,%s,%s)",
                (data["name"], data["price"], data["category"])
            )

            conn.commit()

            return jsonify({"message": "Блюдо добавлено"}), 201

        except Error:

            conn.rollback()
            return jsonify({"message": "Ошибка добавления"}), 400

        finally:
            conn.close()


@app.route("/api/menu/<int:item_id>", methods=["DELETE"])
def delete_menu_item(item_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "DELETE FROM menu WHERE id=%s",
        (item_id,)
    )

    conn.commit()
    conn.close()

    return jsonify({"message": "Блюдо удалено"})


# -------------------------------
# REVIEWS
# -------------------------------
@app.route("/api/reviews", methods=["POST"])
def add_review():

    data = request.json

    conn = get_db_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            INSERT INTO reviews
            (dish_id, client_name, rating, comment)
            VALUES (%s,%s,%s,%s)
            """,
            (
                data["dish_id"],
                data["client_name"],
                data["rating"],
                data["comment"]
            )
        )

        conn.commit()

        return jsonify({"message": "Отзыв добавлен"}), 201

    except Error as e:

        conn.rollback()
        return jsonify({"message": str(e)}), 500

    finally:
        conn.close()


# -------------------------------
# ORDERS
# -------------------------------
@app.route("/api/orders", methods=["GET", "POST"])
def orders():

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Получить заказы
    if request.method == "GET":

        query = """
        SELECT o.id,
               t.table_number,
               o.status,
               o.order_datetime,
               GROUP_CONCAT(CONCAT(oi.dish_name,' x',oi.quantity)
               SEPARATOR ', ') AS dishes
        FROM orders o
        JOIN tables t ON o.table_id = t.id
        JOIN order_items oi ON o.id = oi.order_id
        GROUP BY o.id
        ORDER BY o.order_datetime DESC
        """

        cursor.execute(query)

        orders = cursor.fetchall()

        for order in orders:
            if order["order_datetime"]:
                order["order_datetime"] = order["order_datetime"].strftime("%H:%M")

        conn.close()

        return jsonify(orders)

    # Создать заказ
    if request.method == "POST":

        data = request.json
        cart = data.get("cart", [])

        user_id = data.get("user_id") if data.get("user_id") != 0 else None

        if not cart:
            return jsonify({"message": "Корзина пуста"}), 400

        try:

            cursor.execute(
                "INSERT INTO orders (table_id,created_by,status) VALUES (%s,%s,'открыт')",
                (data["table_id"], user_id)
            )

            order_id = cursor.lastrowid

            for item in cart:

                cursor.execute(
                    """
                    INSERT INTO order_items
                    (order_id,dish_name,quantity)
                    VALUES (%s,%s,%s)
                    """,
                    (
                        order_id,
                        item["name"],
                        item["quantity"]
                    )
                )

            cursor.execute(
                "UPDATE tables SET status='занят' WHERE id=%s",
                (data["table_id"],)
            )

            conn.commit()

            return jsonify({"message": "Заказ оформлен"}), 201

        except Error as e:

            conn.rollback()
            return jsonify({"message": str(e)}), 500

        finally:
            conn.close()


@app.route("/api/orders/<int:order_id>/close", methods=["PUT"])
def close_order(order_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE orders SET status='закрыт' WHERE id=%s",
        (order_id,)
    )

    conn.commit()
    conn.close()

    return jsonify({"message": "Заказ закрыт"})


# -------------------------------
# RUN SERVER
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True, port=5000)