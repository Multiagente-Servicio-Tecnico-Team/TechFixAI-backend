from sqlalchemy import text

from app.database.connection import engine


def obtener_datos_ticket(ticket_id: int):
    consulta = text("""
        SELECT
            t.id,
            t.codigo,
            t.tipo_solicitud,
            t.estado,
            u.nombre,
            u.email
        FROM tickets AS t
        JOIN usuarios AS u
            ON u.id = t.cliente_id
        WHERE t.id = :ticket_id
    """)

    with engine.connect() as connection:
        resultado = connection.execute(
            consulta,
            {"ticket_id": ticket_id}
        ).mappings().first()

        return resultado


ticket = obtener_datos_ticket(1)

if ticket:
    print("Ticket:", ticket["codigo"])
    print("Tipo:", ticket["tipo_solicitud"])
    print("Estado:", ticket["estado"])
    print("Cliente:", ticket["nombre"])
    print("Email:", ticket["email"])
else:
    print("Ticket no encontrado")