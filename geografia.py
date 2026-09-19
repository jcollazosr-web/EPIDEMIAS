# -*- coding: utf-8 -*-
"""
geografia.py — Listas para los menús desplegables de país/departamento/
ciudad, en vez de que el usuario los escriba a mano (evita errores
ortográficos que rompen la geocodificación).

Alcance honesto: cubre Colombia con detalle completo (departamentos +
ciudades principales), y los países de habla hispana / más comunes para
la región. Para cualquier país o ciudad que no esté en la lista, se
ofrece la opción "Otro/a (escribir)" con un campo de texto libre —
nunca se bloquea la captura de un dato real solo porque no está en
esta lista.
"""

PAISES = [
    "Colombia", "Venezuela", "Ecuador", "Perú", "Brasil", "Panamá", "Costa Rica",
    "México", "Argentina", "Chile", "Bolivia", "Paraguay", "Uruguay", "Cuba",
    "República Dominicana", "Guatemala", "Honduras", "El Salvador", "Nicaragua",
    "España", "Estados Unidos", "Canadá",
    "Otro país (escribir)",
]

# Los 32 departamentos + Bogotá D.C. (distrito capital)
DEPARTAMENTOS_COLOMBIA = [
    "Amazonas", "Antioquia", "Arauca", "Atlántico", "Bogotá D.C.", "Bolívar",
    "Boyacá", "Caldas", "Caquetá", "Casanare", "Cauca", "Cesar", "Chocó",
    "Córdoba", "Cundinamarca", "Guainía", "Guaviare", "Huila", "La Guajira",
    "Magdalena", "Meta", "Nariño", "Norte de Santander", "Putumayo", "Quindío",
    "Risaralda", "San Andrés y Providencia", "Santander", "Sucre", "Tolima",
    "Valle del Cauca", "Vaupés", "Vichada",
    "Otro departamento (escribir)",
]

# Ciudades/municipios principales por departamento — NO es una lista
# exhaustiva de los ~1100 municipios de Colombia (evitar inventar datos
# imprecisos). Cubre las cabeceras más grandes de cada departamento;
# cualquier municipio no listado se captura con "Otra ciudad (escribir)".
CIUDADES_POR_DEPARTAMENTO = {
    "Amazonas": ["Leticia", "Puerto Nariño"],
    "Antioquia": ["Medellín", "Bello", "Itagüí", "Envigado", "Rionegro", "Apartadó", "Turbo"],
    "Arauca": ["Arauca", "Saravena", "Tame"],
    "Atlántico": ["Barranquilla", "Soledad", "Malambo", "Sabanalarga"],
    "Bogotá D.C.": ["Bogotá"],
    "Bolívar": ["Cartagena", "Magangué", "Turbaco"],
    "Boyacá": ["Tunja", "Duitama", "Sogamoso", "Chiquinquirá"],
    "Caldas": ["Manizales", "La Dorada", "Chinchiná"],
    "Caquetá": ["Florencia"],
    "Casanare": ["Yopal"],
    "Cauca": ["Popayán", "Santander de Quilichao"],
    "Cesar": ["Valledupar", "Aguachica"],
    "Chocó": ["Quibdó"],
    "Córdoba": ["Montería", "Cereté", "Lorica"],
    "Cundinamarca": ["Soacha", "Zipaquirá", "Facatativá", "Chía", "Girardot"],
    "Guainía": ["Inírida"],
    "Guaviare": ["San José del Guaviare"],
    "Huila": ["Neiva", "Pitalito"],
    "La Guajira": ["Riohacha", "Maicao"],
    "Magdalena": ["Santa Marta", "Ciénaga"],
    "Meta": ["Villavicencio", "Acacías"],
    "Nariño": ["Pasto", "Tumaco", "Ipiales"],
    "Norte de Santander": ["Cúcuta", "Ocaña", "Pamplona"],
    "Putumayo": ["Mocoa", "Puerto Asís"],
    "Quindío": ["Armenia", "Calarcá"],
    "Risaralda": ["Pereira", "Dosquebradas", "Santa Rosa de Cabal"],
    "San Andrés y Providencia": ["San Andrés", "Providencia"],
    "Santander": ["Bucaramanga", "Floridablanca", "Girón", "Barrancabermeja", "Piedecuesta"],
    "Sucre": ["Sincelejo", "Corozal"],
    "Tolima": ["Ibagué", "Espinal"],
    "Valle del Cauca": ["Cali", "Palmira", "Buenaventura", "Tuluá", "Cartago", "Buga"],
    "Vaupés": ["Mitú"],
    "Vichada": ["Puerto Carreño"],
}

OPCION_OTRO = "Otro/a (escribir)"
