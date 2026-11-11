"""Construye el benchmark de componentes con referencias extraídas de fuentes locales."""
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]
MANUAL='app/agents/jerarquico/knowledge_base/manual_servicio.md'
FAQ='app/agents/jerarquico/knowledge_base/faq_servicio.md'
PAIRS=[
(1,'pantalla negra no signal','Mi PC enciende pero el monitor dice No Signal. ¿Qué causas posibles hay y qué debe revisar un técnico?'),
(2,'pantalla azul 0x0000007B','Mi computadora muestra una pantalla azul con el error 0x0000007B y Windows no inicia. ¿Qué podría estar pasando y qué revisión necesita?'),
(3,'PC se apaga poco después de encender','El equipo se apaga inmediatamente después de encender. ¿Qué causas posibles y revisión técnica indica el manual?'),
(4,'Windows se congela en el logo','Windows se queda congelado en el logo al iniciar. ¿Qué problemas posibles hay y qué revisión corresponde?'),
(5,'disco al 100 equipo lento','El disco está al 100 % y la computadora funciona lentamente. ¿Qué puede causarlo y qué debe revisar el técnico?'),
(6,'CPU al 100 system interrupts','El procesador marca CPU al 100 % sin aplicaciones abiertas. ¿Qué causas posibles existen y cómo debe evaluarlo un técnico?'),
(7,'frecuencia CPU baja temperatura elevada','El procesador reduce su frecuencia y la temperatura es alta. ¿Qué causas posibles y revisión de refrigeración corresponden?'),
(8,'memoria RAM casi llena en reposo','La memoria RAM está casi llena aunque no uso programas. ¿Qué causas posibles hay y qué se revisa antes de recomendar más memoria?'),
(9,'laptop batería no carga','La batería de mi laptop no carga y dura poco. ¿Qué posibles causas hay y qué se verifica antes de reemplazarla?'),
(10,'laptop lenta demora abrir aplicaciones','Mi laptop tarda mucho en abrir aplicaciones. ¿Qué puede estar pasando y cuándo se puede considerar un SSD?'),
]
FAQ_CASES=[
('services','Servicios disponibles','¿Qué servicios ofrecen para computadoras y laptops?'),
('location','Ubicación de la tienda','¿Dónde está ubicada la tienda física?'),
('hours','Horario de atención','¿Cuál es el horario de atención?'),
('quotes','Tarifas y cotizaciones','¿Qué tarifas base de mano de obra manejan y cuál es el importe válido?'),
('payments','Pagos','¿Qué medios de pago aceptan y el chat confirma que recibieron dinero?'),
('warranty','Garantía','¿Qué garantía recibe un armado de PC pagado y cómo se confirma la cobertura?'),
('delivery','Retiro y envío','¿Puedo elegir retiro o courier y eso confirma una fecha de entrega?'),
('inventory','Compras y disponibilidad','¿Cómo verifican precios, disponibilidad y compatibilidad de los repuestos?'),
]

def build():
    manual=(ROOT/MANUAL).read_text(encoding='utf-8')
    faq=(ROOT/FAQ).read_text(encoding='utf-8')
    rows=[]
    for number,short,natural in PAIRS:
        match=re.search(rf'(?ms)^- \*\*Caso {number}:.*?(?=^- \*\*Caso |\Z)',manual)
        block=match.group()
        diagnosis=re.search(r'\*\*Diagnóstico\*\*: (.*)',block).group(1)
        solution=re.search(r'\*\*Solución\*\*: (.*)',block).group(1)
        excerpt=diagnosis+'\n'+solution
        for label,question in [('short',short),('natural',natural)]:
            rows.append({'id':f'technical_{number:02d}_{label}','route':'technical','mode':'software' if number in {2,4,6,8} else 'hardware','user_input':question,'reference':diagnosis+' '+solution,'answerable':True,'reference_source':MANUAL,'reference_anchor':f'Caso {number}:','reference_excerpt':excerpt,'reference_sha256':hashlib.sha256(excerpt.encode()).hexdigest(),'expected_source_id':f'manual_servicio:{number:03d}','source_is_demo':False})
    for identifier,section,question in FAQ_CASES:
        block=re.search(rf'(?ms)^## {re.escape(section)}\s*\n(.*?)(?=^## |\Z)',faq).group(1).strip()
        rows.append({'id':'faq_'+identifier,'route':'faq','user_input':question,'reference':block,'answerable':True,'reference_source':FAQ,'reference_anchor':'## '+section,'reference_excerpt':block,'reference_sha256':hashlib.sha256(block.encode()).hexdigest(),'source_is_demo':True})
    for identifier,route,question in [('control_recipe','technical','¿Cuál es la receta de una lasaña vegetariana?'),('control_sports','faq','¿Quién ganó el mundial de fútbol de 1986?')]:
        rows.append({'id':identifier,'route':route,'mode':'hardware','user_input':question,'reference':None,'answerable':False,'reference_source':None,'reference_anchor':None,'reference_excerpt':None,'reference_sha256':None,'source_is_demo':False})
    return {'schema_version':2,'scope':'production_rag_components_not_http_chat','reference_review':'Referencias extraídas de las fuentes y verificadas por código; pendientes de revisión humana independiente.','faq_notice':'La fuente FAQ se declara demostrativa: se evalúa fidelidad al corpus, no veracidad comercial.','rows':rows}

if __name__=='__main__':
    path=Path(__file__).with_name('dataset_project.json')
    path.write_text(json.dumps(build(),ensure_ascii=False,indent=2),encoding='utf-8')
    print('Dataset de 30 casos preparado:',path)