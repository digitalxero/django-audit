from datetime import date

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.db.models.signals import post_save, pre_delete, m2m_changed
from django.utils.encoding import smart_unicode

from audit.models import (AuditTrail, AuditField, AuditedModel,
                          AuditM2MField, AuditGroup, get_formatter)
from audit.signals import audit_special

def get_audit_name(instance):
    audit_name = None
    if hasattr(instance, 'audit_name'):
        audit_name = instance.audit_name
    if not audit_name:
        audit_name = '{name}({pk})'.format(name=ct.model.upper(),
                                               pk=instance.pk)
    elif callable(audit_name):
        audit_name = audit_name()

    return audit_name

def find_field(sender, instance):
    for key, field in instance.audit.fields.iteritems():
        if field.type == instance.audit.type.m2m:
            if key in repr(sender):
                break

    return key

def generate_audits(instance, action):
    ct = ContentType.objects.get_for_model(instance)
    audit_name = get_audit_name(instance)

    admin_audit, _ = AuditTrail.objects.get_or_create(type=0,
                                        content_type=ct, object_id=instance.pk,
                                        action=action, audit_on=date.today())
    admin_audit.name = audit_name
    if not admin_audit.modified_by:
        admin_audit.modified_by = instance.audit.modified_by
    admin_audit.save()

    #Only bother to create a public audit if there are public fields to track
    public_audit = None
    if instance.audit.has_public_fields:
        public_audit, _ = AuditTrail.objects.get_or_create(type=1,
                                        content_type=ct, object_id=instance.pk,
                                        action=action, audit_on=date.today())
        public_audit.name = audit_name
        if not public_audit.modified_by:
            public_audit.modified_by = instance.audit.modified_by
        public_audit.save()

    return admin_audit, public_audit

def add_group(audit, name):
    ag, _ = AuditGroup.objects.get_or_create(audit=audit, name=name)
    ag.save()


#Post Save Signal Handler to Audit all changes
def save_audit(sender, instance=None, created=False, **kwargs):
    if not isinstance(instance, AuditedModel):
        return

    if instance.audit.ignore_next:
        instance.audit.ignore_next = False
        return

    action = 0
    if created:
        action = 1
        instance.audit.ignore_next = True

    admin_audit, public_audit = generate_audits(instance, action)

    #Only track field changes if it was an existing record
    if not created:
        #Admins track all field changes (listed in the admin_audit & public_audit)
        for field, (new, original) in instance.audit.dirty_fields.iteritems():
            add_group(admin_audit, instance.audit.fields[field].group)

            f = AuditField(audit=admin_audit, name=field, new=new,
                           original=original, modified_by=instance.audit.modified_by)
            f.save()

            if instance.audit.fields[field].public:
                add_group(public_audit, instance.audit.fields[field].group)
                f = AuditField(audit=public_audit, name=field, new=new,
                               original=original, modified_by=instance.audit.modified_by)
                f.save()

        for field, changes in instance.audit.m2m_dirty.iteritems():
            add_group(admin_audit, instance.audit.fields[field].group)

            added = ', '.join(changes['added'])
            removed = ', '.join(changes['removed'])
            f = AuditM2MField(audit=admin_audit, name=field, added=added,
                              removed=removed, modified_by=instance.audit.modified_by)
            f.save()

            if instance.audit.fields[field].public:
                add_group(public_audit, instance.audit.fields[field].group)
                f = AuditM2MField(audit=public_audit, name=field, added=added,
                                  removed=removed, modified_by=instance.audit.modified_by)
                f.save()

        instance.audit.dirty_fields.clear()
        instance.audit.m2m_dirty.clear()

def delete_audit(sender, instance, **kwargs):
    if not isinstance(instance, AuditedModel):
        return

    generate_audits(instance, 2)

def special_audit(instance, field, action, value, **kwargs):
    """
    This handles special fields like Generic relations or
    OneToMany relationships. This signal MUST be triggered manually by the
    person wishing to track it
    `instance` is the instance the relationship is TO.
    `field` is the field name in instance.audit.fields
    `action` is the action you are tracking [added|removed]
    `value` is the value the action applies to, can be a pk, or some other value
        You should have a formatter for this in the instance model.
    """
    if not isinstance(instance, AuditedModel):
        return

    formatter = get_formatter(instance, field)
    admin_audit, public_audit = generate_audits(instance, action)
    value = formatter(value)

    added = ''
    removed = ''

    if action == 'added':
        added = value
    elif action == 'removed':
        removed = value

    add_group(admin_audit, instance.audit.fields[field].group)

    f = AuditM2MField(audit=admin_audit, name=field, added=added,
                      removed=removed, modified_by=instance.audit.modified_by)
    f.save()

    if instance.audit.fields[field].public:
        add_group(public_audit, instance.audit.fields[field].group)
        f = AuditM2MField(audit=public_audit, name=field, added=added,
                          removed=removed, modified_by=instance.audit.modified_by)
        f.save()

def m2m_post_add(sender, instance, action, reverse, model, pk_set, **kwargs):
    field = find_field(sender, instance)

    if field not in instance.audit.m2m_dirty:
        instance.audit.m2m_dirty[field] = {'added': [], 'removed': []}

    formatter = get_formatter(instance, field)
    instance.audit.m2m_dirty[field]['added'].extend(map(formatter, pk_set))

def m2m_pre_remove(sender, instance, action, reverse, model, pk_set, **kwargs):
    field = find_field(sender, instance)

    if field not in instance.audit.m2m_dirty:
        instance.audit.m2m_dirty[field] = {'added': [], 'removed': []}

    formatter = get_formatter(instance, field)
    instance.audit.m2m_dirty[field]['removed'].extend(map(formatter, pk_set))

def m2m_pre_clear(sender, instance, action, reverse, model, pk_set, **kwargs):
    pass

def m2m_audit(sender, instance, action, reverse, model, pk_set, **kwargs):
    if not isinstance(instance, AuditedModel) or\
       action not in ['post_add', 'pre_remove', 'pre_clear'] or\
       isinstance(instance, model):
        return

    if action == 'post_add':
        m2m_post_add(sender, instance, action, reverse, model, pk_set, **kwargs)
    elif action == 'pre_remove':
        m2m_pre_remove(sender, instance, action, reverse, model, pk_set, **kwargs)
    elif action == 'pre_clear':
        m2m_pre_clear(sender, instance, action, reverse, model, pk_set, **kwargs)


pre_delete.connect(delete_audit)
post_save.connect(save_audit)
m2m_changed.connect(m2m_audit)
audit_special.connect(special_audit)
