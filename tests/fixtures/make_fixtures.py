"""Generate test subtitle fixtures for test suite."""

from pathlib import Path


def create_all_fixtures(fixtures_dir: Path):
    fixtures_dir.mkdir(parents=True, exist_ok=True)

    # 1. Standard SRT with italics, bold, multi-line, numbers, music
    srt_content = """1
00:00:01,000 --> 00:00:03,500
Hello <i>world</i>!
This is a second line.

2
00:00:04,000 --> 00:00:05,000
♪ ♫ 12345 ♪

3
00:00:06,000 --> 00:00:08,000
[door slams loudly]

4
00:00:09,000 --> 00:00:11,000
این خط قبلاً به فارسی ترجمه شده است.

5
00:00:12,000 --> 00:00:14,000
Thank you very much!
"""
    (fixtures_dir / "sample.srt").write_text(srt_content, encoding="utf-8")

    # 2. SRT with UTF-8 BOM
    (fixtures_dir / "sample_bom.srt").write_bytes(b"\xef\xbb\xbf" + srt_content.encode("utf-8"))

    # 3. SRT with cp1256 encoding (Arabic/Persian Windows)
    cp1256_text = """1
00:00:01,000 --> 00:00:03,000
مرحبا بكم جميعا في هذا الفيلم الجميل

2
00:00:04,000 --> 00:00:06,000
شكرا جزيلا ونراكم في الحلقة القادمة
"""
    (fixtures_dir / "sample_cp1256.srt").write_bytes(cp1256_text.encode("cp1256"))

    # 4. ASS with styles, signs, karaoke, vector drawings, pos and mid-line tags
    ass_content = """[Script Info]
Title: Test Anime Episode
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,55,&H00FFFFFF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,30,30,30,1
Style: Sign,Arial,45,&H00FFFF00,&H000000FF,&H00000000,&H00000000,1,0,0,0,100,100,0,0,1,2,2,8,10,10,10,1
Style: OP_Song,Arial,40,&H00FF00FF,&H000000FF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,2,2,2,10,10,10,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,{\\an8}{\\pos(960,100)}Look at {\\i1}this{\\i0}!\\NIt's amazing!
Dialogue: 0,0:00:03.50,0:00:05.00,Sign,,0,0,0,,Tokyo High School
Dialogue: 0,0:00:05.50,0:00:07.00,OP_Song,,0,0,0,,Opening Song Lyrics
Dialogue: 0,0:00:07.50,0:00:09.00,Default,,0,0,0,,{\\k50}Ka{\\k50}ra{\\k50}o{\\k50}ke
Dialogue: 0,0:00:09.50,0:00:11.00,Default,,0,0,0,,{\\p1}m 0 0 l 100 0 100 100 0 100{\\p0}
Comment: 0,0:00:11.50,0:00:13.00,Default,,0,0,0,,This is a comment line
Dialogue: 0,0:00:13.50,0:00:15.50,Default,,0,0,0,,Good morning, Sensei!
"""
    (fixtures_dir / "sample.ass").write_text(ass_content, encoding="utf-8")

    # 5. WebVTT
    vtt_content = """WEBVTT

00:00:01.000 --> 00:00:03.000
Welcome to the show.

00:00:04.000 --> 00:00:06.000
Enjoy your stay.
"""
    (fixtures_dir / "sample.vtt").write_text(vtt_content, encoding="utf-8")


if __name__ == "__main__":
    create_all_fixtures(Path(__file__).parent)
