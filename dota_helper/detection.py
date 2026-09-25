"""Local calibrated portrait matching. A visual match is a candidate, never proof of lock-in."""
from pathlib import Path
from PIL import Image, ImageChops, ImageStat


def similarity(a, b):
    a = a.convert("RGB").resize((64, 40))
    b = b.convert("RGB").resize((64, 40))
    difference = ImageStat.Stat(ImageChops.difference(a, b))
    return 1 - sum(difference.mean) / (3 * 255)


class Detector:
    def __init__(self, templates):
        self.directory = Path(templates)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.candidate = None
        self.streak = 0

    def inspect(self, frame):
        if sum(ImageStat.Stat(frame.convert("RGB")).stddev) < 12:
            self.candidate, self.streak = None, 0
            return None, 0.0, "Capture is blank or too uniform"
        scores = []
        for path in self.directory.glob("*.png"):
            if path.stem.isdigit():
                with Image.open(path) as reference:
                    scores.append((similarity(frame, reference), int(path.stem)))
        scores.sort(reverse=True)
        if not scores:
            return None, 0.0, "No saved portrait references"
        score, hero_id = scores[0]
        margin = score - scores[1][0] if len(scores) > 1 else 1
        if score < .94 or margin < .035:
            self.candidate, self.streak = None, 0
            return None, score, "Uncertain portrait; select hero manually"
        self.streak = self.streak + 1 if hero_id == self.candidate else 1
        self.candidate = hero_id
        if self.streak < 3:
            return None, score, "Checking agreement across frames"
        return hero_id, score, "Portrait candidate; lock-in requires confirmation or GSI"


def capture(region):
    import mss
    with mss.mss() as screen:
        raw = screen.grab(region)
        return Image.frombytes("RGB", raw.size, raw.rgb)
