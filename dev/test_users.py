"""Create the users which dev/integration_check.py and the browser checks use.

Run in a throwaway InvenTree instance, from its backend directory
(src/backend/InvenTree), with InvenTree's environment set:

    python /path/to/inventree-virtual-bins/dev/test_users.py

It creates three users (password "inventree-test") and prints an API token for
each:

- vb-viewer:   may view stock and stock locations
- vb-operator: may also change stock, but not add it, and not change locations
- vb-nobody:   has no roles at all
"""

import os
import sys

import django

sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'InvenTree.settings')
django.setup()

from django.contrib.auth import get_user_model  # noqa: E402
from django.contrib.auth.models import Group  # noqa: E402

from users.models import ApiToken, RuleSet, UserProfile  # noqa: E402
from users.tasks import update_group_roles  # noqa: E402

ROLES = {
    'vb-viewer': {'stock': ('view',), 'stock_location': ('view',), 'part': ('view',)},
    'vb-operator': {
        'stock': ('view', 'change'),
        'stock_location': ('view',),
        'part': ('view',),
    },
    'vb-nobody': {},
}

User = get_user_model()

for username, roles in ROLES.items():
    user, _ = User.objects.get_or_create(
        username=username, defaults={'email': f'{username}@example.com'}
    )
    user.set_password('inventree-test')
    user.is_active = True
    user.save()

    UserProfile.objects.get_or_create(user=user)

    group, _ = Group.objects.get_or_create(name=username)
    update_group_roles(group)

    for ruleset in RuleSet.objects.filter(group=group):
        allowed = roles.get(ruleset.name, ())
        ruleset.can_view = 'view' in allowed
        ruleset.can_add = 'add' in allowed
        ruleset.can_change = 'change' in allowed
        ruleset.can_delete = 'delete' in allowed
        ruleset.save()

    # Turn the rule sets into the permissions InvenTree's own API checks
    update_group_roles(group)
    user.groups.set([group])

    ApiToken.objects.filter(user=user, name='vb-test').delete()
    token = ApiToken.objects.create(user=user, name='vb-test')

    # The secret is only readable on the object which has just been created
    print(f'{username} {token.token}')
