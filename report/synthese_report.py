from odoo import models, api, fields
from datetime import timedelta, datetime


class ParticularReport(models.AbstractModel):
    _name = 'report.progistack_attendance.report_synthese_partner_view'

    def get_statut(self, presence):
        return presence.order_number

    def get_first_position(self, date_list):

        try:
            return date_list[-1].strftime('%H:%M')
        except:
            pass

    def get_second_position(self, date_list):

        try:
            return date_list[-2].strftime('%H:%M')
        except:
            pass

    def get_last_position(self, date_list):

        try:
            return date_list[-3].strftime('%H:%M')
        except:
            pass

    def conv_time_float(self, value):

        try:
            vals = value.split(':')
            t, hours = divmod(float(vals[0]), 24)
            t, minutes = divmod(float(vals[1]), 60)
            minutes = minutes / 60.0
            return hours + minutes

        except:
            pass

    @api.model
    def _get_report_values(self, docids, data=None):
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        start_date_d = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date_d = datetime.strptime(end_date, '%Y-%m-%d').date()
        delta = end_date_d - start_date_d
        date_between = []
        for n in range(delta.days + 1):
            date_between.append(end_date_d - timedelta(days=n))
        all_presences = self.env['hr.attendance'].sudo().search([
            ('date_pointage', '>=', start_date),
            ('date_pointage', '<=', end_date)])

        att_in = []
        att_out = []

        for presence in all_presences:
            zk_model_date_entree = self.env["zk.report.daily.attendance"].sudo().search(
                [('punch_type', '=', '0'),
                 ('compare_date', '=', presence.date_pointage),
                 ('name', '=', presence.employee_id.name)]).mapped('punching_time')

            zk_model_date_sortie = self.env["zk.report.daily.attendance"].sudo().search(
                [('punch_type', '=', '1'),
                 ('compare_date', '=', presence.date_pointage),
                 ('name', '=', presence.employee_id.name)]).mapped('punching_time')

            att_in.append([presence.date_pointage, presence.employee_id.name, zk_model_date_entree])
            att_out.append([presence.date_pointage, presence.employee_id.name, zk_model_date_sortie])
        return {
            "doc_model": 'hr.attendance',
            'docs': self.env['hr.attendance'].search([]),
            'all_presences': all_presences,
            'date_between': date_between,
            'start_date': start_date,
            'get_first_position': self.get_first_position,
            'get_second_position': self.get_second_position,
            'get_last_position': self.get_last_position,
            'conv_time_float': self.conv_time_float,
            'att_in': att_in,
            'att_out': att_out,
            'end_date': end_date,
            'with_presence': data.get('with_present'),
            'report_type': data.get('report_type') if data else '',
        }
