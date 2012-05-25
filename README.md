This is a fairly comprehensive Audit Trail App for use with standard RDBMS databases. If you are looking for a solution for NoSQL there is a great project by the same name but differing author @ https://launchpad.net/django-audit that uses MongoDB.

Usage
====

    #In Your models.py
    from audit.models import AuditedModel, AuditOptions

    class SomeItem(models.Model):
        name = models.CharField(max_length=100)

    #Notice we are inheriting AuditedModel here to tell the system we want to audit this model
    class YourModel(AuditedModel):
        YOURMODEL_STATUS = ((0, 'New'), (1, 'Waiting Approval'), (2, 'Approved'))
        name = models.CharField(max_length=100)
        status = models.SmallIntegerField(choices=YOURMODEL_STATUS)
        items = models.ManyToManyField(SomeItem)

        ...

        #So far everything seems normal, now we get to the Audit config
        audit = AuditOptions()
        audit.add('name', 'General', audit.type.normal)
        audit.add('status', 'General', audit.type.normal)
        audit.add('items', 'Items', audit.type.m2m)
        #audit.add(FIELD_NAME, GROUP, FIELD_TYPE, public=False)
        #if you set public to true it creates a public audit trail
        #that only tracks changes to fields you set as public
        #There is still the admin only audit trail that tracks
        #changes to all fields you add

        def audit_name(self):
            """You can put whatever you want here, the system
               only records it in the DB but does not used it
               you might use it for filtering or something in your
               own audit history views"""
            return u'YourModel({pk})'.format(pk=self.pk)

        def audit_status_formatter(self, value):
            """audit_FIELD_NAME_formatter lets you decide how you
               want the data for this field to be stored and
               represented in the audit history"""
            if value is None:
                return value

            for idx, v in self.YOURMODEL_STATUS:
                if idx == int(value):
                    return v

        def audit_items_formatter(self, value):
            if value is None:
                return value

            if isinstance(value, models.Model):
                item = value
            else:
                item = SomeItem.objects.get(pk=value)

            return u'{name}'.format(name=item.name)

Ok We have a model we want to audit, now we need to set up the system to actually start auditing

    #In your main urls.py
    from audit.bind import *
    ...

Done! Ok you can run your app and now any change you make to YourModel will be tracked in the audit history.

There are no views or admin sections for this app, as how you wish to display the data is highly personal and left to the developer to generate.

Similar Projects
====
  * [Django Audit for MongoDB](https://launchpad.net/django-audit)
  * [AuditTrail](http://code.djangoproject.com/wiki/AuditTrail)
  * [AuditLog](http://code.google.com/p/django-audit-log/)


NoSQL vs SQL
====
Not all of us can use a NoSQL audit solution due to business rules or other constraints.  Django Audit for MongoDB preserves field type in the audit history, which is lost django-audit for SQL. This loss of field type is mitigated by the field formatters which allow you to record the field how you want to display it to the person reading the audit history.

Ultimately the solution you pick will depend on your requirements and capabilities, both work, though I believe my solution takes a bit more work for the developer to setup and configure on each model then then MongoDB solution (have not looked too deeply into the code over there as I cannot use MongoDB for the projects I need an Audit history in)

Disclaimer
====
The nature of Audit requirements makes it impossible for a one size fits all solution. This solution fits my requirements very well, if it does not fit yours I may or may not be willing to modify it so it does.

Except for bug fixes and feature enhancements I required for my own use I have little to no intention of maintaining this application. I just figured to throw it up here and see if people find it useful or not.