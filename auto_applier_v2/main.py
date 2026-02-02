import sys
import os
import threading

# Truco para que Python encuentre los módulos 'core', 'ui', etc. dentro de esta carpeta
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ui.app import App
from core.engine import AutomationEngine

# Variable global para el motor
current_engine = None

def start_automation(data: dict):
    """Callback: Se ejecuta al pulsar 'Iniciar Búsqueda' en la UI"""
    global current_engine
    
    # Si no se especifica carpeta de usuario, creamos una local
    if "user_data_dir" not in data or not data["user_data_dir"]:
        data["user_data_dir"] = os.path.join(os.getcwd(), "config", "browser_profile")
    
    app.append_log(f"[MAIN] Iniciando motor... (Keywords: {data.get('keywords')})")
    
    # Instanciamos el motor pasándole la cola de logs de la UI
    current_engine = AutomationEngine(ui_log_queue=app.log_queue, user_data=data)
    current_engine.start() # Arranca en un hilo separado

def pause_automation():
    """Callback: Se ejecuta al pulsar 'Pausar'"""
    global current_engine
    if current_engine:
        if current_engine.paused:
            current_engine.resume()
            app.pause_button.configure(text="Pausar", fg_color="#7A1F1F") # Rojo
            app.append_log("[MAIN] Reanudando...")
        else:
            current_engine.pause()
            app.pause_button.configure(text="Reanudar", fg_color="#2E8B57") # Verde
            app.append_log("[MAIN] Pausando...")

if __name__ == "__main__":
    # Aseguramos que existan carpetas básicas
    os.makedirs("config", exist_ok=True)
    
    # Iniciamos la UI
    app = App(on_start=start_automation, on_pause=pause_automation)
    
    # Mensaje de bienvenida en el log
    app.append_log("=== AutoApplier V2 Ready ===")
    app.append_log("Por favor, selecciona la carpeta de tus CVs y configura la búsqueda.")
    
    app.mainloop()