from logging import getLogger

from tps_frontend import DELETION_VIEW_UI_FILE
from tps_frontend.view import View

logger = getLogger(__name__)

class DeletionView(View):
    _ui_file = DELETION_VIEW_UI_FILE
