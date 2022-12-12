from odoo import fields, models
from datetime import date
import datetime
from odoo.exceptions import ValidationError


class DownloadLackAttendance(models.TransientModel):
    _name = 'download.lack.attendance'

    date_from = fields.Date(string="Date de debut", default=lambda self: date.today())
    date_to = fields.Date(string="Date de fin", default=lambda self: date.today())

    def download_lack_attendance(self):

        zk_machine_attendance = self.env['zk.machine.attendance'].search([
            ('punching_time', '>=', self.date_from),
            ('punching_time', '<=', self.date_to)
        ])
        nombre_jour = self.date_to - self.date_from
        if not zk_machine_attendance:
            # raise ValidationError(f"Aucune présence trouvée du {self.date_from} au {self.date_to}")
            employees = self.env['hr.employee'].search([('device_id', '!=', False)])
            for nj in range(nombre_jour.days + 1):
                date_actuelle = self.date_from + datetime.timedelta(days=nj)
                # print("Check in et check out",
                #       datetime.datetime(date_actuelle.year,date_actuelle.month,date_actuelle.day,0,0,0,0),
                #       datetime.datetime(date_actuelle.year,date_actuelle.month,date_actuelle.day,0,0,0,5))
                for employee in employees:
                    presence = self.env['hr.attendance'].create({
                        'employee_id': employee.id,
                        'check_in': datetime.datetime(date_actuelle.year, date_actuelle.month, date_actuelle.day, 0, 0,
                                                      0, 0),
                        'heur_planifie': employee.heur_arrive,
                        'heur_depart': employee.heur_depart,
                        'heure_sortie': 0.00,
                        'heure_entre': 0.00,
                        'tolerance': employee.tolerance,
                        'check_out': datetime.datetime(date_actuelle.year, date_actuelle.month, date_actuelle.day, 0, 0,
                                                       0, 5),
                        'visible': False,
                        'date_pointage': date_actuelle})
                    # print("Presence de no l'absent cree", presence)
            return
        # print("Zk_machine", zk_machine_attendance[0].check_in.date())

        # print(nombre_jour.days)
        for nj in range(nombre_jour.days + 1):
            # print(nj)
            date_actuelle = self.date_from + datetime.timedelta(days=nj)
            presences = self.env['hr.attendance'].search([
                ('date_pointage', '=', date_actuelle)
            ])
            # print("Date actuelle", date_actuelle)
            if not presences:
                zk = zk_machine_attendance.filtered(lambda s: s.punching_time.date() == date_actuelle)
                # print("Zk", zk)
                if zk:
                    employees = self.env['hr.employee'].search([('device_id', '!=', False)])
                    for employee in employees:
                        if zk_machine_attendance.filtered(lambda s: s.employee_id.id == employee.id):
                            zk_employee = zk.filtered(lambda s: s.employee_id.id == employee.id)
                            if zk_employee:
                                pointage_entrees = zk_employee.filtered(lambda s: s.punch_type == '0').mapped(
                                    'punching_time')
                                pointage_sorties = zk_employee.filtered(lambda s: s.punch_type == '1').mapped(
                                    'punching_time')
                                check_in = 0
                                check_out = 0
                                check_in_day = datetime.datetime(date_actuelle.year, date_actuelle.month,
                                                                 date_actuelle.day, 0, 0, 0, 0)
                                check_out_day = datetime.datetime(date_actuelle.year, date_actuelle.month,
                                                                  date_actuelle.day, 0, 0, 0, 5)
                                if pointage_entrees:
                                    # print("Les pointages entrees", pointage_entrees)
                                    check_in = min(pointage_entrees)
                                    # print("Checkin avant", pointage_entrees)
                                    check_in_hour = check_in.time().hour
                                    check_in_minute = check_in.time().minute
                                    # check_in = float(f"{check_in_hour}.{check_in_minute}")
                                    check_in = check_in_hour + check_in_minute / 60
                                    # print("Nouveau checkin", check_in)
                                    check_in_day = datetime.datetime(
                                        date_actuelle.year,
                                        date_actuelle.month,
                                        date_actuelle.day,
                                        hour=check_in_hour,
                                        minute=check_in_minute
                                    )
                                if pointage_sorties:
                                    # print("Pointage sortie")
                                    check_out = max(pointage_sorties)
                                    # check_out = check_out.time()
                                    check_out_hour = check_out.time().hour
                                    check_out_minute = check_out.time().minute
                                    check_out = check_out_hour + check_out_minute / 60
                                    check_out_day = datetime.datetime(
                                        date_actuelle.year,
                                        date_actuelle.month,
                                        date_actuelle.day,
                                        hour=check_out_hour,
                                        minute=check_out_minute
                                    )
                                # print("Check", check_in_day, check_out_day, employee.name)
                                # print("Check out", check_out_day)
                                # print("check_in apres", employee.name, check_in, check_out)
                                if check_in_day < check_out_day:
                                    # print("Check in check out de 1", check_in_day, check_out_day)
                                    presence = self.env['hr.attendance'].create({
                                        'employee_id': employee.id,
                                        'check_in': check_in_day,
                                        'check_out': check_out_day,
                                        'heur_planifie': employee.heur_arrive,
                                        'heur_depart': employee.heur_depart,
                                        'heure_entre': check_in,
                                        'heure_sortie': check_out,
                                        'tolerance': employee.tolerance,
                                        'visible': False,
                                        'is_check': True,
                                        'date_pointage': date_actuelle
                                    })
                                else:
                                    # print("Check in check out de 2222", check_in_day, check_out_day)
                                    presence = self.env['hr.attendance'].create({
                                        'employee_id': employee.id,
                                        'check_in': check_in_day,
                                        # 'check_out': check_out_day,
                                        'heur_planifie': employee.heur_arrive,
                                        'heur_depart': employee.heur_depart,
                                        'heure_entre': check_in,
                                        'heure_sortie': check_out,
                                        'tolerance': employee.tolerance,
                                        'visible': False,
                                        'is_check': True,
                                        'date_pointage': date_actuelle
                                    })
                                    # print("Check out ainsi", presence.check_out)
                                presence._compute_worked_hours()
                                # print("Presence cree", presence.employee_id.name, type(presence.heure_entre))
                        else:
                            # print("Employee qui n'a pas pointe", employee.name)
                            presence = self.env['hr.attendance'].create({
                                'employee_id': employee.id,
                                # 'check_in': date_actuelle,
                                'heur_planifie': employee.heur_arrive,
                                'heur_depart': employee.heur_depart,
                                'heure_sortie': 0.00,
                                'heure_entre': 0.00,
                                'tolerance': employee.tolerance,
                                # 'check_out': 0.0,
                                'visible': False,
                                'date_pointage': date_actuelle})
                            # print("Presence de l'absent cree", presence)
                    # date_pointage_zk = [z.date_pointage for z in zk]
