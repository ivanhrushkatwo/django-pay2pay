# -*- coding: utf-8 -*-

import conf
import logging
import xmltodict
import lxml.etree
import lxml.builder
from django.http import HttpResponse
from django.views.generic import View, TemplateView
from annoying.functions import get_object_or_None
from django.views.decorators.csrf import csrf_exempt
from .utils import get_signature
from .models import Payment

logger = logging.getLogger('pay2pay')


class Confirm(View):
    @csrf_exempt
    def dispatch(self, *args, **kwargs):
        return super(Confirm, self).dispatch(*args, **kwargs)

    def post(self, request, *args, **kwargs):
        error_msg = ''

        xml = request.POST.get('xml', '').replace(' ', '+').decode('base64')
        try:
            response = self._get_obj_response(xml)
        except (ValueError, TypeError):
            response = {}
            logger.error('Can not parse xml', exc_info=True)

        payment = get_object_or_None(Payment, order_id=response.get('order_id'))
        if payment:
            sig_encode = request.POST.get('sign', '')
            sign = get_signature(xml, conf.PAY2PAY_HIDE_KEY)
            if sig_encode == sign:
                # Check the amount
                amount = response.get('amount', 0)
                if payment.amount != float(amount):
                    error_msg = 'Amount does not match'
                    logger.error(error_msg)
                    xml_response = self._get_xml_response(error_msg)
                    return HttpResponse(xml_response)

                try:
                    payment.status = response['status']
                    payment.paymode = response['paymode']
                    payment.trans_id = response['trans_id']
                    payment.error_msg = response.get('error_msg', '')
                    if response.get('test_mode', '') == '1':
                        payment.test_mode = True
                    payment.save()
                    payment.send_signals()
                except KeyError:
                    logger.error('Have not some key at parsed XML data', exc_info=True)
            else:
                error_msg = 'Security check failed'
        else:
            error_msg = 'Unknown order_id'

        if error_msg:
            logger.error(error_msg)

        xml_response = self._get_xml_response(error_msg)
        return HttpResponse(xml_response)

    def _get_xml_response(self, error_msg_value):
        e = lxml.builder.ElementMaker()
        request = e.request
        status = e.status
        error_msg = e.error_msg

        if error_msg_value:
            status_value = 'no'
        else:
            status_value = 'yes'

        request = request(
            status(status_value),
            error_msg(error_msg_value)
        )
        return lxml.etree.tostring(request, encoding='utf-8').replace('\n', '')

    def _get_obj_response(self, xml):
        xml = xml.replace('<?xmlversion="1.0"encoding="UTF-8"?>', '').replace('\n', '')
        return xmltodict.parse(xml)['response']


class PaymentSuccess(TemplateView, Confirm):
    template_name = 'pay2pay/payment_success.html'

    def post(self, request, *args, **kwargs):
        super(PaymentSuccess, self).post(request, *args, **kwargs)
        return super(PaymentSuccess, self).get(request, *args, **kwargs)


class PaymentFail(TemplateView, Confirm):
    template_name = 'pay2pay/payment_fail.html'

    def post(self, request, *args, **kwargs):
        super(PaymentFail, self).post(request, *args, **kwargs)
        return super(PaymentFail, self).get(request, *args, **kwargs)