from fastapi import APIRouter

from api.auth import router as auth_router
from api.search import router as search_router
from api.candidates import router as candidates_router
from api.tracks import router as tracks_router
from api.stream import router as stream_router
from api.streaming import router as streaming_router
from api.lyrics import router as lyrics_router
from api.playlists import router as playlists_router
from api.system import router as system_router
from api.covers import router as covers_router
from api.remote import router as remote_router
from api.task_import import router as task_import_router

# Единый агрегатор всех модульных API роутеров.
# ВАЖНО: Статические маршруты регистрируются ДО параметризованных {id}:
# 1. /tracks/search и /tracks/candidates регистрируются до /tracks/{track_id}
# 2. /stream/next и /stream/discovery регистрируются до /stream/{track_id}
api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(search_router)
api_router.include_router(candidates_router)
api_router.include_router(tracks_router)
api_router.include_router(stream_router)
api_router.include_router(streaming_router)
api_router.include_router(lyrics_router)
api_router.include_router(playlists_router)
api_router.include_router(system_router)
api_router.include_router(covers_router)
api_router.include_router(remote_router)
api_router.include_router(task_import_router)
