from flask import Blueprint

main = Blueprint("main", __name__)

from . import auth, inbound, internal, tools
