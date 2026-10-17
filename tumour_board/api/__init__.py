"""HTTP routers added for the new interface (/tb-nik), one module per area. Each exports `router`, an APIRouter without a prefix,
included by routes.tumour_board_routes.setup_tumour_board_routes() under /api/tb. Shared helpers live in common.py."""
