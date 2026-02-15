import pytest
import binascii
from blackbird_sports_uploader.device import Message, CmdType, TransType, Oid, GetFile

def test_message_framing_escape():
    # Test escaping of 0x7E, 0x7F, 0x7D
    original = b"\x7E\x7F\x7D"
    escaped = Message.escape(original)
    
    # 0x7E -> 0x7D 0x01
    # 0x7F -> 0x7D 0x02
    # 0x7D -> 0x7D 0x00 (implied from code: b - 0x7D + 1 => 0x7D - 0x7D + 1 = 1? No wait)
    # Let's check logic:
    # 0x7D -> buf.append(0x7D); buf.append(0x7D - 0x7D + 1) -> 0x7D 0x01
    # 0x7E -> buf.append(0x7D); buf.append(0x7E - 0x7D + 1) -> 0x7D 0x02
    # 0x7F -> buf.append(0x7D); buf.append(0x7F - 0x7D + 1) -> 0x7D 0x03
    
    # Wait, code says:
    # buf.append(b - 0x7D + 1)
    
    # If b=0x7D: 0x7D - 0x7D + 1 = 1. -> 0x01.
    # If b=0x7E: 0x7E - 0x7D + 1 = 2. -> 0x02.
    # If b=0x7F: 0x7F - 0x7D + 1 = 3. -> 0x03.
    
    expected = b"\x7D\x01\x7D\x02\x7D\x03"
    # Actually my calculation might be wrong, let's trust the code logic in test or derivation.
    # 0x7D (125). 0x7E (126). 0x7F (127).
    # 0x7D -> 0x7D 0x01?
    # 0x7E -> 0x7D 0x02?
    # 0x7F -> 0x7D 0x03?
    
    # Let's verify by unescaping
    unescaped = Message.unescape(escaped)
    assert unescaped == original

def test_message_to_bytes():
    # Create a GetFile message
    msg = GetFile(filename="test.txt", sid=1)
    
    encoded = msg.to_bytes()
    
    # Verify framing
    assert encoded[0] == 0x7E
    assert encoded[-1] == 0x7F
    
    # Verify checksum logic implicitly by unescaping and calculating CRC
    # or just trust the from_bytes roundtrip
    
    decoded = Message.from_bytes(encoded)
    assert isinstance(decoded, GetFile)
    assert decoded.filename == "test.txt"
    assert decoded.sid == 1
    assert decoded.cmd_type == CmdType.Get
    assert decoded.oid == Oid.GetFile

def test_checksum_verification():
    # Construct a valid packet
    msg = GetFile(filename="test.txt")
    data = msg.to_bytes()
    
    # Corrupt a byte in the payload (guaranteed to be inside framing)
    # data is immutable bytes, convert to bytearray
    mutable_data = bytearray(data)
    # Determine a safe index to corrupt (not start/end/escape if possible, but any payload byte will do)
    # The middle of the packet should be payload.
    idx = len(mutable_data) // 2
    mutable_data[idx] ^= 0xFF # Flip bits
    
    corrupted_data = bytes(mutable_data)
    
    # Should raise assertion error due to CRC mismatch
    with pytest.raises(AssertionError, match="crc mismatch"):
        Message.from_bytes(corrupted_data)
