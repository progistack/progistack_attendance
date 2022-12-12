from odoo import fields, models, _
from datetime import date
import datetime
from odoo.exceptions import UserError, ValidationError
from ..models.zkconst import *
import logging

# from datetime import datetime as time

_logger = logging.getLogger(__name__)
try:
    from zk import ZK, const
except ImportError:
    _logger.error("Veuillez installer la bibliothèque pyzk.")

_logger = logging.getLogger(__name__)


class DownloadMachineAttendance(models.TransientModel):
    _name = 'download.machine.attendance'

    date_from = fields.Date(string="Date de debut", default=lambda self: date.today())
    date_to = fields.Date(string="Date de fin", default=lambda self: date.today())

    def to_update_check_in(self):
        active_id = self.env.context.get('active_id')
        zk_attendance = self.env['zk.machine.attendance'].sudo().search([('compare', '>=', self.date_from),
                                                                         ('compare', '<=', self.date_to)])
        for val in zk_attendance:
            val.write({'check_in': val.compare})

    def download_machine_attendance(self):
        active_id = self.env.context.get('active_id')
        zk_attendance = self.env['zk.machine.attendance']

        zk_machine = self.env['zk.machine'].sudo().search([('id', '=', active_id)])

        for info in zk_machine:
            machine_ip = info.name
            zk_port = info.port_no
            timeout = 5

            try:
                zk = ZK(machine_ip, port=zk_port, timeout=timeout, password=0, force_udp=False, ommit_ping=False)
            except NameError:
                raise UserError(_("Module Pyzk introuvable. Veuillez l'installer avec 'pip3 install pyzk'."))
            conn = zk_machine.device_connect(zk)

            if conn:
                # conn.disable_device() #Device Cannot be used during this time.
                try:
                    user = conn.get_users()

                except:
                    user = False

                try:
                    attendance = conn.get_attendance()
                    for each in attendance:
                        pointing_date = each.timestamp.date()
                        atten_time = datetime.strptime(each.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                                                       '%Y-%m-%d %H:%M:%S')
                        if self.date_from <= pointing_date <= self.date_to:
                            get_user_id = self.env['hr.employee'].sudo().search(
                                [('device_id', '=', each.user_id)])
                            duplicate_atten_ids = zk_attendance.sudo().search(
                                [('device_id', '=', each.user_id), ('punching_time', '=', atten_time)])

                            if user:
                                for uid in user:
                                    if uid.user_id == each.user_id:
                                        if get_user_id:
                                            if not duplicate_atten_ids:

                                                if info.device_type == "entree":
                                                    zk_attendance.sudo().create({
                                                        'employee_id': get_user_id.id,
                                                        'device_id': each.user_id,
                                                        'punch_type': '0',
                                                        'punching_time': atten_time,
                                                        'compare_date': pointing_date,
                                                        'compare': str(pointing_date)
                                                    })

                                                else:
                                                    zk_attendance.sudo().create({'employee_id': get_user_id.id,
                                                                                 'device_id': each.user_id,
                                                                                 'punch_type': '1',
                                                                                 'punching_time': atten_time,
                                                                                 'compare_date': pointing_date,
                                                                                 'compare': str(pointing_date)})


                except:
                    pass
