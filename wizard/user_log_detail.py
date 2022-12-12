from odoo import fields, models


class UserLogDetail(models.TransientModel):
    _name = 'log.detail'

    name = fields.Many2one('hr.employee', string='Employee')
    punching_day = fields.Datetime(string='Date')
