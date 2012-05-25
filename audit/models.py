import uuid
from collections import namedtuple

from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.utils.encoding import smart_unicode

def _field_formatter(value):
    if value is not None:
        return smart_unicode(value)

    return value

def get_formatter(obj, attr):
    aff = 'audit_{field}_formatter'.format(field=attr)
    return getattr(obj, aff) if hasattr(obj, aff) else _field_formatter

class AuditOptions(object):
    def __init__(self):
        self.field = namedtuple('field', ['name', 'group', 'type', 'public'])
        self.fields = {}
        self.dirty_fields = {}
        self.m2m_dirty = {}
        self.modified_by = None
        self.type = self._Types()
        self.ignore_next = False
        self._has_pfs = False

    def add(self, name, group, type=0, public=False):
        if type not in self.type:
            raise AttributeError('Unknown type')

        f = self.field(name, group, type, public)
        self.fields[name] = f

        if public:
            self._has_pfs = True

    def _get_has_public_fields(self):
        return self._has_pfs
    has_public_fields = property(_get_has_public_fields)

    #Types
    class _Types(object):
        _types_ = [0, 1, 2]
        def __contains__(self, value):
            return value in self._types_

        def _get_normal(self):
            return 0
        normal = property(_get_normal)

        def _get_m2m(self):
            return 1
        m2m = property(_get_m2m)

        def _get_special(self):
            return 2
        special = property(_get_special)



class AuditedModel(models.Model):
    """
    Auditable Model
    `admin_audit` is a list of admin_only audit fields
    `member_audit` is a list of all member viewable audit fields

    Admins will track fields in both lists, so you do not need to
    add fields in both lists
    """

    def assign_user(self, user):
        if not isinstance(user, User):
            raise AttributeError("user must be an instance of User")
        self.audit.modified_by = user

    def __setattr__(self, attr, value):
        if hasattr(self, attr):
            current = getattr(self, attr)
            if not attr.startswith('_') and current != value:
                field_formatter = get_formatter(self, attr)
                if (attr in self.audit.fields):
                    orig =  field_formatter(current)
                    new = field_formatter(value)
                    self.audit.dirty_fields[attr] = (new, orig)

        super(AuditedModel, self).__setattr__(attr, value)

    class Meta:
        abstract = True


class AuditManager(models.Manager):
    def audit_for(self, obj):
        ct = ContentType.objects.get_for_model(obj)
        return self.filter(content_type=ct, object_id=obj.id)[:7]


class AuditTrail(models.Model):
    AUDIT_TYPES = [(0, 'Admin'), (1, 'Public')]
    AUDIT_ACTIONS = [(0, 'Modified'), (1, 'Created'), (2, 'Deleted')]

    content_type = models.ForeignKey(ContentType, null=True)
    object_id = models.PositiveIntegerField(null=True)
    content_object = generic.GenericForeignKey('content_type', 'object_id')

    #Audit Info
    name = models.CharField(max_length=100, blank=True, null=True)
    type = models.SmallIntegerField(choices=AUDIT_TYPES, db_index=True)
    action = models.SmallIntegerField(choices=AUDIT_ACTIONS)

    audit_on = models.DateField()
    modified_by = models.ForeignKey(User, null=True)

    objects = AuditManager()

    class Meta:
        ordering = ['-audit_on']

class AuditGroup(models.Model):
    audit = models.ForeignKey(AuditTrail, related_name='groups')
    name = models.CharField(max_length=100)

class FieldBase(models.Model):
    name = models.CharField(max_length=100)
    audit_on = models.DateTimeField(auto_now_add=True)
    modified_by = models.ForeignKey(User)

    class Meta:
        abstract = True

class AuditField(FieldBase):
    audit = models.ForeignKey(AuditTrail, related_name='fields')
    original = models.TextField(blank=True, null=True)
    new = models.TextField(blank=True, null=True)


class AuditM2MField(FieldBase):
    audit = models.ForeignKey(AuditTrail, related_name='m2m_fields')
    removed = models.TextField(blank=True, null=True)
    added = models.TextField(blank=True, null=True)


