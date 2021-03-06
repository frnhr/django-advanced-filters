# Generated by Django 2.1.8 on 2019-04-12 15:38

from django.db import migrations, models


def populate_model_name(apps, schema_editor):
    AdvancedFilter = apps.get_model('advanced_filters', 'AdvancedFilter')
    for af in AdvancedFilter.objects.all():
        try:
            af.model_name = af.model.split('.')[1]
        except IndexError:
            af.model_name = af.model
        af.save()


class Migration(migrations.Migration):

    dependencies = [
        ('advanced_filters', '0003_auto_20180610_0718'),
    ]

    operations = [
        migrations.AddField(
            model_name='advancedfilter',
            name='model_name',
            field=models.CharField(blank=True, max_length=64, null=True, verbose_name='model', editable=False),
        ),
        migrations.RunPython(populate_model_name, migrations.RunPython.noop)
    ]
