"""Attaching files: summaries for each kind, copying into the workspace, @file parsing."""
import zipfile

from PIL import Image

from agent import attach


def test_text_pdf_zip_sheet_and_unknown(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    (src / "notes.txt").write_text("remember the milk", encoding="utf-8")
    (src / "t.csv").write_text("a,b\n1,2\n3,4\n", encoding="utf-8")
    with zipfile.ZipFile(src / "z.zip", "w") as z:
        z.writestr("inner.txt", "x")
    (src / "blob.bin").write_bytes(b"\x00\x01\x02" * 100)
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(str(src / "r.pdf")); c.drawString(72, 700, "Quarterly report text"); c.save()
    note, imgs = attach.prepare([src / n for n in ("notes.txt", "t.csv", "z.zip", "blob.bin", "r.pdf")], ws)
    assert "remember the milk" in note and "3 row(s)" in note and "inner.txt" in note
    assert "binary file" in note and "Quarterly report" in note and "1 page" in note
    assert (ws / "uploads" / "notes.txt").exists() and not imgs


def test_image_is_queued_for_vision_and_never_overwrites(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    Image.new("RGB", (40, 30), "pink").save(tmp_path / "p.png")
    n1, i1 = attach.prepare([tmp_path / "p.png"], ws)
    n2, i2 = attach.prepare([tmp_path / "p.png"], ws)
    assert "40x30" in n1 and len(i1) == 1 and i1[0][0].endswith("p.png")
    assert (ws / "uploads" / "p (2).png").exists() and i2[0][0].endswith("p (2).png")


def test_secret_files_and_missing_files_are_refused(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (tmp_path / "id_rsa").write_text("KEY", encoding="utf-8")
    note, imgs = attach.prepare([tmp_path / "id_rsa", tmp_path / "nope.txt"], ws, denied=lambda p: p.name == "id_rsa")
    assert "blocked" in note and "not a file" in note and not (ws / "uploads").exists()


def test_extract_paths_from_a_typed_line(tmp_path):
    a = tmp_path / "my file.txt"; a.write_text("x")
    b = tmp_path / "pic.png"; b.write_text("x")
    text, found = attach.extract_paths(f'summarize @"{a}" and look at @{b} please, mail me@example.com')
    assert found == [str(a), str(b)]
    assert text == "summarize and look at please, mail me@example.com"
    text, found = attach.extract_paths(f'what is "{a}"?')           # a path dragged into the terminal
    assert found == [str(a)] and text == "what is ?"
    assert attach.extract_paths("@nothing.txt hi") == ("@nothing.txt hi", [])


def test_video_gets_frames_and_info(tmp_path):
    import shutil
    import subprocess
    if not shutil.which("ffmpeg"):
        return
    ws = tmp_path / "ws"; ws.mkdir()
    v = tmp_path / "clip.mp4"
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "testsrc=duration=2:size=160x120:rate=10",
                    "-pix_fmt", "yuv420p", str(v)], check=True)
    note, imgs = attach.prepare([v], ws)
    assert "Video" in note and "160" in note and len(imgs) == attach.MAX_FRAMES
    assert all(__import__("pathlib").Path(p).exists() for p, _ in imgs)
