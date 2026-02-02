import os
from datetime import datetime

import pandas as pd


class JobTracker:
    def __init__(self, filename: str = "tracking_ofertas.xlsx") -> None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.filepath = os.path.join(base_dir, filename)
        self._ensure_file_exists()

    def _ensure_file_exists(self) -> None:
        if not os.path.exists(self.filepath):
            df = pd.DataFrame(
                columns=[
                    "Fecha",
                    "Hora",
                    "Puesto",
                    "Empresa",
                    "Estado",
                    "Motivo/Detalle",
                    "URL",
                ]
            )
            df.to_excel(self.filepath, index=False)

    def track_job(self, job_data: dict, status: str, details: str = "") -> None:
        try:
            now = datetime.now()
            new_row = {
                "Fecha": now.strftime("%Y-%m-%d"),
                "Hora": now.strftime("%H:%M:%S"),
                "Puesto": job_data.get("title", "N/A"),
                "Empresa": job_data.get("company", "N/A"),
                "Estado": status,
                "Motivo/Detalle": details,
                "URL": job_data.get("url", "N/A"),
            }

            df = pd.read_excel(self.filepath)
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            df.to_excel(self.filepath, index=False)
            print(f"[TRACKER] Guardado: {status} - {job_data.get('title')}")
        except Exception as exc:
            print(f"[TRACKER] Error guardando Excel: {exc}")
