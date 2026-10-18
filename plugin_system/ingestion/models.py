"""
Модели данных и стандартизированный контракт кандидата трека (Unified Candidate).
Обеспечивает 100% унификацию полей для всех источников (P2P, SourceA, SourceAs, SourceC, SourceD).
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict, field


@dataclass
class UnifiedCandidate:
    candidate_id: str
    source: str
    source_name: str
    artist: str
    title: str
    version_type: str = "original"
    version_label: str = "Original"
    format: str = "mp3"
    bitrate: int = 320
    duration: str = ""
    dl_url: Optional[str] = None
    song_url: Optional[str] = None
    img_url: Optional[str] = None
    score: int = 0
    size: int = 0
    peer: Optional[str] = None
    filename: Optional[str] = None
    free_slot: bool = False
    queue_len: int = 0
    speed: int = 0
    plugin_name: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Для обратной совместимости поднимаем track_id если он есть в extra
        if "track_id" in self.extra and "track_id" not in d:
            d["track_id"] = self.extra["track_id"]
        return d


def make_candidate(
    candidate_id: str,
    source: str,
    source_name: str,
    artist: str,
    title: str,
    version_type: str = "original",
    version_label: str = "Original",
    format: str = "mp3",
    bitrate: int = 320,
    duration: str = "",
    dl_url: Optional[str] = None,
    song_url: Optional[str] = None,
    img_url: Optional[str] = None,
    score: int = 0,
    size: int = 0,
    peer: Optional[str] = None,
    filename: Optional[str] = None,
    free_slot: bool = False,
    queue_len: int = 0,
    speed: int = 0,
    plugin_name: Optional[str] = None,
    **extra
) -> Dict[str, Any]:
    """
    Фабрика создания унифицированного словаря кандидата.
    Гарантирует наличие всех базовых полей с типизированными значениями по умолчанию.
    """
    cand = UnifiedCandidate(
        candidate_id=candidate_id,
        source=source.lower(),
        source_name=source_name,
        artist=artist.strip(),
        title=title.strip(),
        version_type=version_type.lower().replace(" ", "_"),
        version_label=version_label,
        format=format.lower(),
        bitrate=int(bitrate) if bitrate else 320,
        duration=duration.strip() if duration else "",
        dl_url=dl_url,
        song_url=song_url,
        img_url=img_url,
        score=int(score),
        size=int(size) if size else 0,
        peer=peer,
        filename=filename,
        free_slot=bool(free_slot),
        queue_len=int(queue_len) if queue_len else 0,
        speed=int(speed) if speed else 0,
        plugin_name=plugin_name,
        extra=extra
    )
    res = cand.to_dict()
    # Разворачиваем extra в корень для удобного доступа к специфичным полям источников
    for k, v in extra.items():
        if k not in res:
            res[k] = v
    return res
