from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0002_userprofile_usd_to_cop_rate'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='type',
            field=models.CharField(
                choices=[('income', 'Ingreso'), ('expense', 'Egreso'), ('transfer', 'Transferencia')],
                max_length=20,
            ),
        ),
    ]
