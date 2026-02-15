import fitdecode
import hashlib
import time
from typing import List, Dict, Any
import xml.etree.ElementTree as ET
from xml.dom import minidom
from logger import setup_logging

logger = setup_logging(__name__)


class FitProcessor:
    def __init__(self, fit_file_path: str, account_id: int):
        self.fit_file_path = fit_file_path
        self.account_id = account_id
        self.points: List[Dict[str, Any]] = []
        self.laps: List[Any] = []
        self.session: Dict[str, Any] = {}
        self.start_time: float = 0.0
        self.total_distance: float = 0.0
        self.total_duration: float = 0.0
        self.score: int = 0
        self.max_speed: float = 0.0
        self.avg_speed: float = 0.0

    def parse(self) -> None:
        """Parse the FIT file and extract relevant data."""
        logger.info(f"Parsing FIT file: {self.fit_file_path}")
        try:
            with fitdecode.FitReader(self.fit_file_path) as fit:
                for frame in fit:
                    if isinstance(frame, fitdecode.FitDataMessage):
                        if frame.name == "record":
                            self._process_record(frame)
                        elif frame.name == "session":
                            self._process_session(frame)
                        elif frame.name == "lap":
                            self._process_lap(frame)
            logger.info(f"Parsing completed. Found {len(self.points)} points.")
        except Exception as e:
            logger.error(f"Error parsing FIT file: {e}")
            raise

    def _process_record(self, frame: fitdecode.FitDataMessage) -> None:
        """Extract fields from a record message."""
        lat = 0.0
        lng = 0.0
        alt = 0.0
        speed = 0.0
        heart_rate = 0
        cadence = 0
        power = 0
        timestamp = 0.0

        if frame.has_field("position_lat") and frame.has_field("position_long"):
            # semicircles to degrees
            lat_val = frame.get_value("position_lat")
            lng_val = frame.get_value("position_long")
            if lat_val is not None:
                lat = lat_val * (180 / 2**31)
            if lng_val is not None:
                lng = lng_val * (180 / 2**31)

        if frame.has_field("altitude"):
            val = frame.get_value("altitude")
            if val is not None:
                alt = float(val)

        if frame.has_field("enhanced_speed"):
            val = frame.get_value("enhanced_speed")
            if val is not None:
                speed = float(val)
        elif frame.has_field("speed"):
            val = frame.get_value("speed")
            if val is not None:
                speed = float(val)

        if frame.has_field("heart_rate"):
            val = frame.get_value("heart_rate")
            if val is not None:
                heart_rate = int(val)

        if frame.has_field("cadence"):
            val = frame.get_value("cadence")
            if val is not None:
                cadence = int(val)

        if frame.has_field("power"):
            val = frame.get_value("power")
            if val is not None:
                power = int(val)

        if frame.has_field("timestamp"):
            val = frame.get_value("timestamp")
            if val is not None:
                timestamp = val.timestamp()

        self.points.append(
            {
                "lat": lat,
                "lng": lng,
                "alt": int(alt),  # App uses int for altitude
                "speed": speed,  # m/s
                "heart_rate": heart_rate,
                "cadence": cadence,
                "power": power,
                "timestamp": timestamp,  # float seconds
            }
        )

    def _process_session(self, frame: fitdecode.FitDataMessage) -> None:
        """Extract fields from session message."""
        if frame.has_field("total_elapsed_time"):
            val = frame.get_value("total_elapsed_time")
            if val is not None:
                self.total_duration = float(val)
        if frame.has_field("total_distance"):
            val = frame.get_value("total_distance")
            if val is not None:
                self.total_distance = float(val)
        if frame.has_field("start_time"):
            val = frame.get_value("start_time")
            if val is not None:
                self.start_time = val.timestamp() * 1000  # ms

        if frame.has_field("max_speed"):
            val = frame.get_value("max_speed")
            if val is not None:
                self.max_speed = float(val)

        if frame.has_field("avg_speed"):
            val = frame.get_value("avg_speed")
            if val is not None:
                self.avg_speed = float(val)

    def _process_lap(self, frame: fitdecode.FitDataMessage) -> None:
        """Extract fields from lap message (placeholder)."""
        pass

    def generate_xml(self) -> str:
        """Generate the proprietary XML format string."""
        logger.debug("Generating XML content")

        if not self.points:
            logger.warning("No points found, generating empty record")
            start_time_ms = int(time.time() * 1000)
            end_time_ms = start_time_ms
        else:
            start_time_ms = (
                int(self.points[0]["timestamp"] * 1000)
                if self.points[0]["timestamp"]
                else int(time.time() * 1000)
            )
            # Ensure end time is correct
            end_time_ms = (
                int(self.points[-1]["timestamp"] * 1000)
                if self.points[-1]["timestamp"]
                else start_time_ms
            )

        self.score = 0

        start_lat = self.points[0]["lat"] if self.points else 39.0
        start_lng = self.points[0]["lng"] if self.points else 116.0
        start_alt = self.points[0]["alt"] if self.points else 0

        end_lat = self.points[-1]["lat"] if self.points else 39.0
        end_lng = self.points[-1]["lng"] if self.points else 116.0
        end_alt = self.points[-1]["alt"] if self.points else 0

        # Build XML
        root = ET.Element("record")
        ET.SubElement(root, "version").text = "5"

        track_elem = ET.SubElement(root, "track")
        start_ts = self.points[0]["timestamp"] if self.points else 0

        track_parts = []
        for i, p in enumerate(self.points):
            ts = p["timestamp"]
            elapsed = int(ts - start_ts)

            # Speed in m/h
            speed_mh = int(p["speed"] * 3600)

            line = f"{p['lat']:.6f},{p['lng']:.6f},{p['alt']},{speed_mh},{p['heart_rate']},{p['cadence']},{p['power']},{elapsed},{elapsed};"
            track_parts.append(line)

        track_elem.text = "".join(track_parts)

        ET.SubElement(root, "trackTimeFrame").text = "10"
        ET.SubElement(root, "pace")
        ET.SubElement(root, "segments")

        start_elem = ET.SubElement(root, "start")
        ET.SubElement(start_elem, "lat").text = f"{start_lat:.6f}"
        ET.SubElement(start_elem, "lng").text = f"{start_lng:.6f}"
        ET.SubElement(start_elem, "height").text = str(int(start_alt))
        ET.SubElement(start_elem, "time").text = str(start_time_ms)

        end_elem = ET.SubElement(root, "end")
        ET.SubElement(end_elem, "lat").text = f"{end_lat:.6f}"
        ET.SubElement(end_elem, "lng").text = f"{end_lng:.6f}"
        ET.SubElement(end_elem, "height").text = str(int(end_alt))
        ET.SubElement(end_elem, "time").text = str(end_time_ms)

        ET.SubElement(root, "duration").text = str(int(self.total_duration))
        ET.SubElement(root, "distance").text = str(int(self.total_distance))

        # Averages/Maxes
        ET.SubElement(root, "maxPace").text = "0"
        ET.SubElement(root, "avgPace").text = "0"
        ET.SubElement(root, "maxSpeed").text = str(int(self.max_speed * 3600))
        ET.SubElement(root, "avgSpeed").text = str(int(self.avg_speed * 3600))
        ET.SubElement(root, "sumHeight").text = "0"
        ET.SubElement(root, "sumHeightDistance").text = "0"
        ET.SubElement(root, "sumHeightTime").text = "0"
        ET.SubElement(root, "calories").text = "0"
        ET.SubElement(root, "score").text = str(self.score)

        # Temperature
        ET.SubElement(root, "maxTemperature").text = ""
        ET.SubElement(root, "minTemperature").text = ""
        ET.SubElement(root, "avgTemperature").text = ""

        ET.SubElement(root, "source").text = "android"

        # Checksum / Close
        checksum = start_time_ms + int(self.total_distance) + self.score
        ET.SubElement(root, "close").text = str(checksum)

        # Fingerprint
        fp_str = (
            f"{self.account_id},{start_time_ms},{int(self.total_distance)},{self.score}"
        )
        fp_hash = hashlib.md5(fp_str.encode()).hexdigest()
        ET.SubElement(root, "fingerPrint").text = fp_hash

        # Pretty print
        xml_str = minidom.parseString(ET.tostring(root)).toprettyxml(indent="    ")
        return xml_str
