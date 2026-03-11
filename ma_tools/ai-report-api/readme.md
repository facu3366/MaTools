# AI Report Assistant — Ejecutar en local

Pasos para correr el proyecto.

Abrir la carpeta del proyecto en **Cursor**.

Abrir una **terminal** y ejecutar lo siguiente.

---

## 1. Crear entorno virtual

```bash
python -m venv venv
```

---

## 2. Activar entorno

Windows:

```bash
venv\Scripts\activate
```

Mac / Linux:

```bash
source venv/bin/activate
```

---

## 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

## 4. Ejecutar el servidor

Desde la carpeta raíz del proyecto:

```bash
uvicorn Backend.main:app --reload
```

---

## 5. Abrir la app

Ir a:

```
http://127.0.0.1:8000/chat
```

---

Listo.
