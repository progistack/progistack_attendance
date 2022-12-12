from odoo import fields, models, api


class SequenceLog(models.Model):
    _name = "sequence.log"

    sequence_day = fields.Integer(string='Sequence Jour', default=1)

    @api.model
    def generate_day_value(self):
        init_value = max(self.env['sequence.log'].search([]).mapped('sequence_day'))
        value = 1
        if init_value:
            value = value + 1
            self.env['sequence.log'].create({'sequence_day': value})

