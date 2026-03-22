"""
Database package for BudgetBandhu ML
Contains MongoDB manager and schema definitions.
"""
from database.mongo_manager import MongoManager
from database.schema import *

__all__ = ['MongoManager']
