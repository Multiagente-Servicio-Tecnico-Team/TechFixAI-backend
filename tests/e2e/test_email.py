import asyncio
import os

from dotenv import load_dotenv

from app.email.email_service import render_ticket_created, send_email


load_dotenv()


async def main():
    html = render_ticket_created(
        nombre_cliente="José",
        ticket_id=322,
        tipo_solicitud="Soporte técnico",
        estado="Pendiente",
    )

    await send_email(
        destinatario=os.getenv("TEST_EMAIL_TO"),
        asunto="Ticket #322 registrado",
        html=html,
    )

    print("Correo enviado correctamente.")


asyncio.run(main())