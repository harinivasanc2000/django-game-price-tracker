# If history page errors with AttributeError on timezone.timedelta,
# in apps/games/views.py replace:
#   HISTORY_PRUNE_INTERVAL = timezone.timedelta(hours=24)
#   HISTORY_PRUNE_MARK = timezone.timedelta(days=60)
# with:
#   from datetime import timedelta
#   HISTORY_PRUNE_INTERVAL = timedelta(hours=24)
#   HISTORY_PRUNE_MARK = timedelta(days=60)
