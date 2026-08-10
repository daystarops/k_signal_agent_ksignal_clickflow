from .models import CaptureVersion
def append_capture(node,capture:CaptureVersion): node.capture_versions.append(capture); node.current_access_status=capture.access_status; node.last_captured_at=capture.captured_at; return node
