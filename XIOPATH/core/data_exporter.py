import json
import csv
from pathlib import Path
from datetime import datetime

class DataExporter:
    MAX_EXPORT_SIZE = 50 * 1024 * 1024  # 50 MB default limit (adjustable via admin panel)

    def __init__(self):
        self.export_dir = Path("data/exports")
        self.export_dir.mkdir(parents=True, exist_ok=True)

    def export(self, data: str, format_type: str = "txt", requester: str = "user") -> str:
        """
        Export data based on demand from either the user or a subagent.
        F-21: Enforces size limit to prevent unbounded disk writes.
        
        Args:
            data: The string data to export (can be JSON string).
            format_type: json, csv, or txt.
            requester: The entity requesting the export ('user', 'subagent_data_processor', etc.)
        """
        data_size = len(data.encode('utf-8'))
        if data_size > self.MAX_EXPORT_SIZE:
            raise ValueError(
                f"Export data ({data_size / (1024*1024):.1f}MB) exceeds "
                f"{self.MAX_EXPORT_SIZE // (1024*1024)}MB limit"
            )
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{requester}_export_{timestamp}.{format_type}"
        file_path = self.export_dir / filename
        
        if format_type == "json":
            try:
                # Try to parse and pretty-print if it's already JSON
                parsed = json.loads(data)
                with open(file_path, "w") as f:
                    json.dump(parsed, f, indent=4)
            except json.JSONDecodeError:
                # If it's not valid JSON, wrap it in a JSON object
                with open(file_path, "w") as f:
                    json.dump({"raw_data": data}, f, indent=4)
        else:
            with open(file_path, "w") as f:
                f.write(data)
                
        return str(file_path.absolute())
