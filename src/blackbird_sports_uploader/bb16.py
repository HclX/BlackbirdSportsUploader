
import asyncio
import binascii
import os
from typing import List, Type, ClassVar, Tuple, Dict, Any, TypeVar
from enum import Enum

from bleak import BleakClient
from bleak.exc import BleakDeviceNotFoundError
from pure_protobuf.annotations import Field, ZigZagInt
from pure_protobuf.message import BaseMessage
from typing_extensions import Annotated
from pydantic import BaseModel, ConfigDict

from .config import settings
from .logger import setup_logging

logger = setup_logging(__name__)


UUID_COMMON_GET = "0000fda1-0000-1000-8000-00805f9b34fb"
UUID_COMMON_POST = "0000fda2-0000-1000-8000-00805f9b34fb"
UUID_COMMON_PUSH = "0000fda3-0000-1000-8000-00805f9b34fb"
UUID_COMMON_SERVICE = "0000fda0-0000-1000-8000-00805f9b34fb"
UUID_OTA_NOTIFY = "0000fd09-0000-1000-8000-00805f9b34fb"
UUID_OTA_SERVICE = "0000fd00-0000-1000-8000-00805f9b34fb"
UUID_OTA_WRITE = "0000fd0a-0000-1000-8000-00805f9b34fb"


class CmdType(Enum):
    Get = 0x00
    Post = 0x01
    Push = 0x02


class TransType(Enum):
    Default = 0x00
    Response = 0x01
    Ack = 0x02


class Oid(Enum):
    Invalid = 0x00
    CheckPower = 0x40
    GetCustomer = 0x34
    GetDeviceInfo = 0x01
    GetFile = 0x29
    GetFileStatus = 0x32
    GetFunction = 0x04
    GetHistory = 0x15
    GetStorage = 0x33
    GetSupport = 0x05
    OffDevice = 0x3F
    PostDeleteFile = 0x2A
    PostFileInfo = 0x2B
    PostReset = 0x03
    PostStopFile = 0x2D
    PostUtcInfo = 0x02
    ReceiveFile = 0x2C
    ResultPower = 0x41
    RunInfo = 0x2710
    RunStart = 0x2711
    SaveDevice = 0x3E
    ScanDevice = 0x3D
    TestCmd = 0xFF
    Unknown = 0xFFFF


T = TypeVar("T", bound="Message")


class Message(BaseModel):
    _REGISTRY: ClassVar[Dict[Tuple[CmdType, TransType, Oid], Type["Message"]]] = {}

    _trans_type: ClassVar[TransType] = TransType.Default
    _cmd_type: ClassVar[CmdType] = CmdType.Get
    _oid: ClassVar[Oid] = Oid.Invalid

    model_config = ConfigDict(frozen=True)
    sid: int = 0

    @property
    def oid(self) -> Oid:
        return self.__class__._oid

    @property
    def cmd_type(self) -> CmdType:
        return self.__class__._cmd_type

    @property
    def trans_type(self) -> TransType:
        return self.__class__._trans_type

    @staticmethod
    # The packet uses 0x7e as start, 0x7f as end, so we need to escape those bytes
    # in the payload. The escape character is 0x7d.
    def escape(data: bytes):
        buf = bytearray()
        for b in data:
            if b in (0x7D, 0x7E, 0x7F):
                buf.append(0x7D)
                buf.append(b - 0x7D + 1)
            else:
                buf.append(b)
        return bytes(buf)

    @staticmethod
    def unescape(data: bytes):
        buf = bytearray()
        i = 0
        while i < len(data):
            b = data[i]
            if b == 0x7D:
                i += 1
                assert i < len(data), (
                    f"Invalid escape sequence at end of packet: {data.hex()}"
                )
                assert data[i] > 0, (
                    f"Invalid escape sequence value: {data[i]:02x} at {i}"
                )
                assert data[i] < 4, (
                    f"Invalid escape sequence value: {data[i]:02x} at {i}"
                )
                buf.append(data[i] + 0x7D - 1)
            else:
                buf.append(b)
            i += 1
        return bytes(buf)

    @classmethod
    def from_bytes(cls: Type[T], data: bytes):
        assert data[0] == 0x7E, f"Invalid start byte: {data[0]:02x}"
        assert data[-1] == 0x7F, f"Invalid end byte: {data[-1]:02x}"

        data = cls.unescape(data[1:-1])

        crc = int.from_bytes(data[-2:], "big")
        crc_calc = binascii.crc_hqx(data[:-2], 0xFFFF)
        assert crc == crc_calc, f"crc mismatch: {crc=:04x} != {crc_calc=:04x}"

        assert len(data) >= 5, f"Invalid packet length: {len(data)}"
        length = int.from_bytes(data[1:3], "big")
        assert length == len(data), f"Invalid packet length: {length}"

        cmd_type = CmdType(data[0] >> 6)
        trans_type = TransType((data[0] >> 4) & 0x03)

        sid = data[0] & 0x0F

        if trans_type == TransType.Ack:
            assert len(data) == 5, f"Invalid packet length: {len(data)}"
            oid = Oid.Invalid
            payload = b""
        else:
            assert len(data) >= 7, f"Invalid packet length: {len(data)}"
            oid = Oid(int.from_bytes(data[3:5], "big"))
            payload = data[5:-2]

        cls_key = (cmd_type, trans_type, oid)
        target_class = cls._REGISTRY.get(cls_key)
        if not target_class:
            raise ValueError(f"Unknown Packet type: {cls_key}")
        kwargs = target_class.parse_payload(payload)
        return target_class(sid=sid, **kwargs)

    @classmethod
    def __init_subclass__(
        cls,
        cmd_type: CmdType = CmdType.Get,
        trans_type: TransType = TransType.Default,
        oid: Oid = Oid.Invalid,
        **kwargs,
    ):
        """Automatically registers child classes when they are defined."""
        super().__init_subclass__(**kwargs)
        cls.cmd_type = cmd_type
        cls.trans_type = trans_type
        cls.oid = oid
        key = (cmd_type, trans_type, oid)
        assert key not in cls._REGISTRY, (
            f"Duplicate key: {key}, {cls._REGISTRY[key]} vs {cls}"
        )
        cls._REGISTRY[key] = cls

    @classmethod
    def parse_payload(cls: Type[T], payload: bytes) -> Dict[str, Any]:
        return {}

    def export_payload(self) -> bytes:
        return b""

    def to_bytes(self, sid_override: int = 0) -> bytes:
        buf = bytearray()

        if sid_override == 0:
            sid_override = self.sid

        buf.append(
            self.cmd_type.value << 6
            | self.trans_type.value << 4
            | (sid_override & 0x0F)
        )
        if self.trans_type == TransType.Ack:
            payload = b""
        else:
            payload = self.oid.value.to_bytes(2, "big") + self.export_payload()

        length = len(payload) + 5
        buf.extend(length.to_bytes(2, "big"))
        buf.extend(payload)

        crc = binascii.crc_hqx(buf, 0xFFFF)
        buf.extend(crc.to_bytes(2, "big"))

        return b"\x7e" + self.escape(buf) + b"\x7f"

    def ack(self) -> "Message":
        cmd_type = self.cmd_type
        return self.__class__._REGISTRY[(cmd_type, TransType.Ack, Oid.Invalid)](
            sid=self.sid
        )

    def __str__(self):
        return self.__repr__()


class GetAck(Message, trans_type=TransType.Ack, cmd_type=CmdType.Push):
    pass


class PushAck(Message, trans_type=TransType.Ack, cmd_type=CmdType.Get):
    pass


class PacketStream:
    def __init__(self, client: BleakClient, char_uuid: str):
        self.client = client
        self.char_uuid = char_uuid
        self.seq = 0
        self.rx_buf = b""
        self.rx_sem = asyncio.Semaphore(0)
        self.rx_messages: List[Message] = []

    def on_notify(self, _: str, data: bytes):
        logger.debug(f"RX({self.char_uuid}): {data.hex()}")

        self.rx_buf += data
        assert self.rx_buf[0] == 0x7E
        if self.rx_buf[-1] == 0x7F:
            message = Message.from_bytes(self.rx_buf)
            self.rx_messages.append(message)
            self.rx_sem.release()
            self.rx_buf = b""

    def clear(self):
        self.rx_buf = b""
        self.rx_messages.clear()
        self.rx_sem = asyncio.Semaphore(0)

    @classmethod
    async def create(cls, client: BleakClient, char_uuid: str):
        stream = cls(client, char_uuid)
        await client.start_notify(char_uuid, stream.on_notify)
        await asyncio.sleep(1)
        return stream

    async def write(self, message: Message):
        data = message.to_bytes(sid_override=self.seq)
        logger.debug(f"TX({self.char_uuid}): {data.hex()}")
        await self.client.write_gatt_char(self.char_uuid, data)

    async def read(self, timeout: int = 60) -> Message:
        try:
            await asyncio.wait_for(self.rx_sem.acquire(), timeout)
            message = self.rx_messages.pop(0)
            assert message.sid == self.seq, f"Invalid sid: {message.sid} != {self.seq}"
            await self.write(message.ack())
            self.seq = (self.seq + 1) & 0x0F
            return message
        except asyncio.TimeoutError:
            raise TimeoutError("No data received within timeout")

    async def close(self):
        await self.client.stop_notify(self.char_uuid)


class GetDeviceInfoRequest(Message, oid=Oid.GetDeviceInfo):
    pass


class DevType(Enum):
    DEV_TYPE_HANDWATCH = 0
    DEV_TYPE_HUB = 1
    DEV_TYPE_BIKE_COMPUTER = 2


class FileTransSize(Enum):
    FILE_TRANS_SIZE_128 = 0
    FILE_TRANS_SIZE_256 = 1
    FILE_TRANS_SIZE_512 = 2
    FILE_TRANS_SIZE_1024 = 3


class GetDeviceInfoResponse(
    Message, oid=Oid.GetDeviceInfo, trans_type=TransType.Response
):
    class _ProtoDef(BaseModel, BaseMessage):
        dev_type: Annotated[int, Field(1)]
        file_trans_size: Annotated[int, Field(2)] = FileTransSize.FILE_TRANS_SIZE_512.value
        hardware_version: Annotated[str, Field(3)]
        software_version: Annotated[str, Field(4)]
        serial_number: Annotated[str, Field(5)]
        protocol_version: Annotated[str, Field(6)]
        ble_mtu: Annotated[int, Field(7)]

    dev_type: DevType
    file_trans_size: FileTransSize
    hardware_version: str
    software_version: str
    serial_number: str
    protocol_version: str
    ble_mtu: int

    @classmethod
    def parse_payload(cls, payload: bytes):
        params = cls._ProtoDef.loads(payload)
        return {
            "dev_type": DevType(params.dev_type),
            "file_trans_size": FileTransSize(params.file_trans_size),
            "hardware_version": params.hardware_version,
            "software_version": params.software_version,
            "serial_number": params.serial_number,
            "protocol_version": params.protocol_version,
            "ble_mtu": params.ble_mtu,
        }

    def export_payload(self) -> bytes:
        return self._ProtoDef(
            dev_type=self.dev_type.value,
            file_trans_size=self.file_trans_size.value,
            hardware_version=self.hardware_version,
            software_version=self.software_version,
            serial_number=self.serial_number,
            protocol_version=self.protocol_version,
            ble_mtu=self.ble_mtu,
        ).dumps()


class GetFile(Message, oid=Oid.GetFile):
    class _ProtoDef(BaseModel, BaseMessage):
        filename: Annotated[str, Field(1)]

    filename: str

    @classmethod
    def parse_payload(cls, payload: bytes):
        params = cls._ProtoDef.loads(payload)
        return {"filename": params.filename}

    def export_payload(self) -> bytes:
        return self._ProtoDef(filename=self.filename).dumps()


class GetFileResponse(Message, oid=Oid.GetFile, trans_type=TransType.Response):
    class _ProtoDef(BaseModel, BaseMessage):
        exist: Annotated[bool, Field(1)] = False

    exist: bool

    @classmethod
    def parse_payload(cls, payload: bytes):
        params = cls._ProtoDef.loads(payload)
        return {"exist": params.exist}

    def export_payload(self) -> bytes:
        return self._ProtoDef(exist=self.exist).dumps()


class GetFileStatus(Message, oid=Oid.GetFileStatus):
    pass


class GetFileStatusResponse(
    Message, oid=Oid.GetFileStatus, trans_type=TransType.Response
):
    pass


class FileInfo(Message, oid=Oid.PostFileInfo, cmd_type=CmdType.Push):
    class _ProtoDef(BaseModel, BaseMessage):
        filename: Annotated[str, Field(1)]
        size: Annotated[ZigZagInt, Field(2)]

    filename: str
    size: int

    @classmethod
    def parse_payload(cls, payload: bytes):
        params = cls._ProtoDef.loads(payload)
        return {"filename": params.filename, "size": params.size}

    def export_payload(self) -> bytes:
        return self._ProtoDef(filename=self.filename, size=self.size).dumps()


class ReceiveFileFlag(Enum):
    First = 0x00
    Middle = 0x01
    Last = 0x02
    Single = 0x03


class ReceiveFile(Message, oid=Oid.ReceiveFile, cmd_type=CmdType.Push):
    seq: int
    flag: ReceiveFileFlag
    data: bytes

    @classmethod
    def parse_payload(cls, payload: bytes):
        return {
            "seq": payload[0],
            "flag": ReceiveFileFlag(payload[1]),
            "data": payload[2:],
        }

    def export_payload(self) -> bytes:
        return (
            self.seq.to_bytes(1, "big") + self.flag.value.to_bytes(1, "big") + self.data
        )

class BB16:
    def __init__(self, address: str):
        self.address = address
        self.cmd_seq = 0
        self.data_seq = 0

    async def connect(self):
        self.client = BleakClient(self.address)
        await self.client.connect(timeout=20.0)
        self.get_stream = await PacketStream.create(self.client, UUID_COMMON_GET)
        self.push_stream = await PacketStream.create(self.client, UUID_COMMON_PUSH)
        self.post_stream = await PacketStream.create(self.client, UUID_COMMON_POST)

    async def disconnect(self):
        await self.get_stream.close()
        await self.push_stream.close()
        await self.post_stream.close()
        await self.client.disconnect()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def download_file(self, filename: str, save_dir: str | None = None) -> bytes:
        logger.info(f"Downloading {filename}...")
        await self.get_stream.write(GetFile(filename=filename))

        resp: GetFileResponse = await self.get_stream.read()
        logger.debug(f"get_file cmd resp: {resp}")
        if not resp.exist:
            logger.error(f"File {filename} does not exist")
            return None

        fileInfo: FileInfo = await self.push_stream.read()
        logger.debug(f"get_file post data: {fileInfo}")

        fileData = bytearray()
        while True:
            frag: ReceiveFile = await self.push_stream.read()
            fileData.extend(frag.data)
            logger.debug(f"Downloaded {filename}... {len(fileData)} / {fileInfo.size}")
            if frag.flag in (ReceiveFileFlag.Last, ReceiveFileFlag.Single):
                break

        if save_dir:
            local_name = os.path.join(save_dir, filename)
            logger.info(f"Saving {filename} to {local_name}...")
            with open(local_name, "wb") as f:
                f.write(fileData)

        return bytes(fileData)

    async def download_files(self, save_dir: str, *filenames: str):
        for filename in filenames:
            await self.download_file(filename, save_dir=save_dir)

    async def download_records(self, save_dir: str) -> List[str]:
        data = await self.download_file("filelist.txt", save_dir=save_dir)
        filenames = []
        for line in data.decode().strip().split("\n"):
            name, size_str = line.strip().split(" ")
            size = int(size_str)

            local_name = os.path.join(save_dir, name)
            if os.path.exists(local_name) and os.path.getsize(local_name) == size:
                logger.warning(f"File {name}({size} bytes) already exists, skipping...")
                continue

            await self.download_file(name, save_dir=save_dir)
            filenames.append(name)

        return filenames

    async def sync(self, data_dir: str = "data") -> List[str]:
        await self.get_stream.write(GetDeviceInfoRequest())
        devInfo: GetDeviceInfoResponse = await self.get_stream.read()
        logger.info(f"Device info: {devInfo}")

        await self.get_stream.write(GetFileStatus())
        fileStatus: GetFileStatusResponse = await self.get_stream.read()
        logger.debug(f"File status: {fileStatus}")

        updated_records = await self.download_records(data_dir)
        await self.download_files(
            data_dir,
            "Setting.json",
            "debug_info.txt",
            "SensorDevice.txt",
            "SensorSearch.txt",
        )

        return updated_records

async def _run(address, data_dir):
    logger.info(f"Connecting to device {address}...")

    async with BB16(address) as bb16:
        updated_records = await bb16.sync(data_dir)
        logger.info(f"Updated records: {updated_records}")

def download() -> bool:
    # Run the async function
    address = settings.BLE_ADDRESS
    assert address, "BLE_ADDRESS not set in settings."

    data_dir = str(settings.DATA_DIR)
    os.makedirs(data_dir, exist_ok=True)

    try:
        asyncio.run(_run(address, data_dir))
    except BleakDeviceNotFoundError:
        logger.error(f"Device {address} not found...")
        return False
    except Exception as e:
        logger.error(f"Error during BLE connection: {e}")
        return False
    return True
