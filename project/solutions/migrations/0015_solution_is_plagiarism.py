# Generated manually: three-state plagiarism flag on Solution

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('solutions', '0014_auto_20200627_1640'),
    ]

    operations = [
        migrations.AddField(
            model_name='solution',
            name='is_plagiarism',
            field=models.BooleanField(blank=True, default=None, null=True),
        ),
    ]
