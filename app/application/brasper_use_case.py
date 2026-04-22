import os
from datetime import datetime, timezone
from urllib.parse import quote

import httpx


class BrasperUseCase:
    def __init__(self):
        self.base_url = os.getenv("BRASPER_API_BASE_URL", "https://apibras.finzeler.com").rstrip("/")
        self.whatsapp_number = os.getenv("BRASPER_WHATSAPP_NUMBER", "51966991933")
        self.allowed_pairs = {
            ("BRL", "PEN"),
            ("PEN", "BRL"),
            ("BRL", "USD"),
            ("USD", "BRL"),
        }

    def _headers(self):
        return {"accept": "application/json"}

    def _fetch_list(self, path: str):
        with httpx.Client(timeout=20.0) as client:
            response = client.get(f"{self.base_url}{path}", headers=self._headers())
            response.raise_for_status()
            payload = response.json()
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("results", "items", "data"):
                if isinstance(payload.get(key), list):
                    return payload[key]
        return []

    def _normalize_currency(self, value):
        if value is None:
            return None
        return str(value).strip().upper()

    def _parse_amount(self, value):
        if value is None:
            return None
        try:
            return round(float(value), 2)
        except (TypeError, ValueError):
            return None

    def _parse_datetime(self, value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None

    def _is_valid_pair(self, origin_currency, destination_currency):
        return (origin_currency, destination_currency) in self.allowed_pairs

    def _copy(self, language: str):
        catalog = {
            "es": {
                "invalid_pair": "Brasper solo opera BRL a PEN, PEN a BRL, BRL a USD y USD a BRL.",
                "missing_pair": "Necesito la moneda de origen y la moneda de destino para cotizar.",
                "missing_amount": "Necesito el monto a enviar o el monto a recibir para hacer la cotización.",
                "quote_title": "Cotización Brasper",
                "send_label": "Monto a enviar",
                "rate_label": "Tipo de cambio",
                "commission_label": "Comisión",
                "net_label": "Neto a convertir",
                "receive_label": "Total a recibir",
                "coupon_label": "Cupón aplicado",
                "coupon_savings": "Ahorro estimado",
                "coupon_available": "Cupón disponible",
                "summary": "Para tu operación de {amount_send} {origin_currency}, recibirás {amount_receive} {destination_currency}.",
                "advisor": "Para seguir con un asesor, abrí el enlace de WhatsApp abajo.",
                "advisor_prefill_hint": "Mensaje sugerido para el asesor (se abre en WhatsApp; podés editarlo):",
            },
            "pt": {
                "invalid_pair": "A Brasper opera apenas BRL para PEN, PEN para BRL, BRL para USD e USD para BRL.",
                "missing_pair": "Preciso da moeda de origem e da moeda de destino para cotar.",
                "missing_amount": "Preciso do valor a enviar ou do valor a receber para fazer a cotação.",
                "quote_title": "Cotação Brasper",
                "send_label": "Valor a enviar",
                "rate_label": "Taxa de câmbio",
                "commission_label": "Comissão",
                "net_label": "Líquido a converter",
                "receive_label": "Total a receber",
                "coupon_label": "Cupom aplicado",
                "coupon_savings": "Economia estimada",
                "coupon_available": "Cupom disponível",
                "summary": "Para sua operação de {amount_send} {origin_currency}, você receberá {amount_receive} {destination_currency}.",
                "advisor": "Para falar com um assessor, use o link do WhatsApp abaixo.",
                "advisor_prefill_hint": "Mensagem sugerida para o assessor (abre no WhatsApp; você pode editar):",
            },
            "en": {
                "invalid_pair": "Brasper currently supports only BRL to PEN, PEN to BRL, BRL to USD, and USD to BRL.",
                "missing_pair": "I need the origin currency and destination currency to quote.",
                "missing_amount": "I need the amount to send or receive to prepare the quote.",
                "quote_title": "Brasper quote",
                "send_label": "Amount to send",
                "rate_label": "Exchange rate",
                "commission_label": "Commission",
                "net_label": "Net to convert",
                "receive_label": "Total to receive",
                "coupon_label": "Coupon applied",
                "coupon_savings": "Estimated savings",
                "coupon_available": "Available coupon",
                "summary": "For your operation of {amount_send} {origin_currency}, you will receive {amount_receive} {destination_currency}.",
                "advisor": "To speak with an advisor, open the WhatsApp link below.",
                "advisor_prefill_hint": "Suggested message for the advisor (opens in WhatsApp; you can edit it):",
            },
        }
        return catalog.get(language, catalog["es"])

    def _round(self, value):
        return round((float(value) + 1e-9) * 100) / 100

    def _fmt(self, value):
        return f"{self._round(value):.2f}"

    def get_supported_currencies(self, args=None):
        currencies = self._fetch_list("/coin/currencies")
        allowed = {"BRL", "PEN", "USD"}
        normalized = []
        seen = set()
        for item in currencies:
            code = self._normalize_currency(item.get("code") or item.get("coin") or item.get("name"))
            if code in allowed and code not in seen:
                seen.add(code)
                normalized.append({"code": code})
        pairs = [
            {"origin_currency": origin, "destination_currency": destination}
            for origin, destination in sorted(self.allowed_pairs)
        ]
        return {"currencies": normalized, "pairs": pairs}

    def get_exchange_rates(self, args=None):
        args = args or {}
        origin_currency = self._normalize_currency(args.get("origin_currency"))
        destination_currency = self._normalize_currency(args.get("destination_currency"))
        raw = self._fetch_list("/coin/tax-rate")
        rates = []
        for item in raw:
            coin_a = self._normalize_currency(item.get("coin_a"))
            coin_b = self._normalize_currency(item.get("coin_b"))
            if not self._is_valid_pair(coin_a, coin_b):
                continue
            if origin_currency and coin_a != origin_currency:
                continue
            if destination_currency and coin_b != destination_currency:
                continue
            rates.append({
                "id": item.get("id"),
                "origin_currency": coin_a,
                "destination_currency": coin_b,
                "rate": float(item.get("tax", 0)),
                "updated_at": item.get("updated_at"),
            })
        return {"rates": rates}

    def get_commission_ranges(self, args=None):
        args = args or {}
        origin_currency = self._normalize_currency(args.get("origin_currency"))
        destination_currency = self._normalize_currency(args.get("destination_currency"))
        raw = self._fetch_list("/coin/commission")
        ranges = []
        for item in raw:
            coin_a = self._normalize_currency(item.get("coin_a"))
            coin_b = self._normalize_currency(item.get("coin_b"))
            if not self._is_valid_pair(coin_a, coin_b):
                continue
            if origin_currency and coin_a != origin_currency:
                continue
            if destination_currency and coin_b != destination_currency:
                continue
            ranges.append({
                "id": item.get("id"),
                "origin_currency": coin_a,
                "destination_currency": coin_b,
                "percentage": float(item.get("percentage", 0)),
                "reverse": float(item.get("reverse", 0) or 0),
                "min_amount": float(item.get("min_amount", 0)),
                "max_amount": float(item.get("max_amount", 0)),
                "updated_at": item.get("updated_at"),
            })
        ranges.sort(key=lambda item: item["min_amount"])
        return {"commission_ranges": ranges}

    def get_active_coupons(self, args=None):
        args = args or {}
        origin_currency = self._normalize_currency(args.get("origin_currency"))
        destination_currency = self._normalize_currency(args.get("destination_currency"))
        now = datetime.now(timezone.utc)
        raw = self._fetch_list("/transactions/coupons/")
        coupons = []
        for item in raw:
            if not item.get("is_active"):
                continue
            coupon_origin = self._normalize_currency(item.get("origin_currency"))
            coupon_destination = self._normalize_currency(item.get("destination_currency"))
            if origin_currency and coupon_origin != origin_currency:
                continue
            if destination_currency and coupon_destination != destination_currency:
                continue
            start_date = self._parse_datetime(item.get("start_date"))
            end_date = self._parse_datetime(item.get("end_date"))
            if start_date and start_date > now:
                continue
            if end_date and end_date < now:
                continue
            coupons.append({
                "id": item.get("id"),
                "code": item.get("code"),
                "discount_percentage": float(item.get("discount_percentage", 0)),
                "origin_currency": coupon_origin,
                "destination_currency": coupon_destination,
                "start_date": item.get("start_date"),
                "end_date": item.get("end_date"),
            })
        return {"coupons": coupons}

    def _get_rate(self, origin_currency, destination_currency):
        rates = self.get_exchange_rates({
            "origin_currency": origin_currency,
            "destination_currency": destination_currency,
        })["rates"]
        return rates[0] if rates else None

    def _get_commissions(self, origin_currency, destination_currency):
        return self.get_commission_ranges({
            "origin_currency": origin_currency,
            "destination_currency": destination_currency,
        })["commission_ranges"]

    def _get_best_coupon(self, origin_currency, destination_currency):
        coupons = self.get_active_coupons({
            "origin_currency": origin_currency,
            "destination_currency": destination_currency,
        })["coupons"]
        if not coupons:
            return None
        return sorted(coupons, key=lambda item: item["discount_percentage"], reverse=True)[0]

    def _range_for_amount(self, ranges, amount):
        if not ranges:
            return None
        for range_item in ranges:
            if range_item["min_amount"] <= amount <= range_item["max_amount"]:
                return range_item
        return ranges[-1]

    def _get_commission_rate_for_amount(self, ranges, amount):
        selected = self._range_for_amount(ranges, amount)
        if not selected:
            return 0.03
        return selected["percentage"] / 100

    def _coupon_discount_amount(self, coupon, base_commission):
        if not coupon or base_commission <= 0:
            return 0.0
        return min(
            self._round(base_commission * (coupon["discount_percentage"] / 100)),
            base_commission,
        )

    def _coupon_discount_fraction(self, coupon, base_commission):
        if not coupon or base_commission <= 0:
            return 0.0
        return min(max(coupon["discount_percentage"] / 100, 0), 1)

    def _estimate_base_amount_send_from_receive(self, desired_receive, rate, ranges, coupon):
        normalized_desired_receive = self._round(desired_receive)
        estimate_send = max(self._round(normalized_desired_receive / rate), 0.01)

        for _ in range(24):
            commission_rate = self._get_commission_rate_for_amount(ranges, estimate_send)
            base_commission = self._round(estimate_send * commission_rate)
            coupon_discount_amount = self._coupon_discount_amount(coupon, base_commission)
            actual_commission = self._round(max(base_commission - coupon_discount_amount, 0))
            net_amount = self._round(estimate_send - actual_commission)
            if net_amount <= 0:
                break
            next_estimate = self._round((normalized_desired_receive / rate) * (estimate_send / net_amount))
            if abs(next_estimate - estimate_send) < 0.001:
                estimate_send = next_estimate
                break
            estimate_send = next_estimate

        return estimate_send

    def _quote_from_gross_send(self, amount_send, rate, ranges, coupon):
        """Cotiza a partir del monto bruto que paga el cliente (igual que la app Brasper)."""
        normalized_amount_send = self._round(amount_send)
        commission_rate = self._get_commission_rate_for_amount(ranges, normalized_amount_send)
        base_commission = self._round(normalized_amount_send * commission_rate)
        coupon_discount_amount = self._coupon_discount_amount(coupon, base_commission)
        commission_net = self._round(max(base_commission - coupon_discount_amount, 0))
        total_to_send = self._round(normalized_amount_send - commission_net)
        amount_receive = self._round(total_to_send * rate)
        selected = self._range_for_amount(ranges, normalized_amount_send)
        return {
            "amount_send": normalized_amount_send,
            "amount_send_without_promotion": normalized_amount_send,
            "amount_receive": amount_receive,
            "rate": float(rate),
            # commission neta (tras cupón sobre comisión): lo que resta del bruto para convertir
            "commission": commission_net,
            # comisión bruta (antes del cupón): es la que muestra la app en "Comisión"
            "commission_gross": base_commission,
            "commission_rate": self._round(commission_rate * 100),
            "total_to_send": total_to_send,
            "coupon_discount": self._round(
                (coupon_discount_amount / base_commission) * 100
            ) if base_commission > 0 else 0,
            "coupon_code": coupon["code"] if coupon else None,
            "coupon_savings_amount": coupon_discount_amount,
            "commission_id": selected["id"] if selected else None,
        }

    def _calculate_direct(self, amount_send, rate, ranges, coupon):
        return self._quote_from_gross_send(amount_send, rate, ranges, coupon)

    def _calculate_inverse(self, desired_receive, rate, ranges, coupon):
        target = self._round(desired_receive)
        base_amount_send = self._estimate_base_amount_send_from_receive(target, rate, ranges, coupon)
        base_amount_send = self._round(max(base_amount_send, 0.01))
        q = self._quote_from_gross_send(base_amount_send, rate, ranges, coupon)
        best = dict(q)
        best_err = abs(q["amount_receive"] - target)
        for _ in range(600):
            if best_err <= 0.005:
                break
            if q["amount_receive"] < target - 0.002:
                base_amount_send = self._round(base_amount_send + 0.01)
            elif q["amount_receive"] > target + 0.002:
                base_amount_send = self._round(max(0.01, base_amount_send - 0.01))
            else:
                break
            q = self._quote_from_gross_send(base_amount_send, rate, ranges, coupon)
            err = abs(q["amount_receive"] - target)
            if err < best_err:
                best_err = err
                best = dict(q)
        return best

    def quote_exchange_operation(self, args=None):
        args = args or {}
        language = args.get("language", "es")
        copy = self._copy(language)
        origin_currency = self._normalize_currency(args.get("origin_currency"))
        destination_currency = self._normalize_currency(args.get("destination_currency"))
        mode = str(args.get("mode") or args.get("quote_mode") or "send").lower()
        amount = self._parse_amount(args.get("amount"))
        if amount is None:
            amount = self._parse_amount(args.get("send_amount"))
            if amount is not None:
                mode = "send"
        if amount is None:
            amount = self._parse_amount(args.get("receive_amount"))
            if amount is not None:
                mode = "receive"

        if not origin_currency or not destination_currency:
            return {"error": copy["missing_pair"], "language": language}
        if not self._is_valid_pair(origin_currency, destination_currency):
            return {"error": copy["invalid_pair"], "language": language}
        if amount is None or amount <= 0:
            return {"error": copy["missing_amount"], "language": language}

        rate_data = self._get_rate(origin_currency, destination_currency)
        if not rate_data:
            return {"error": copy["invalid_pair"], "language": language}
        ranges = self._get_commissions(origin_currency, destination_currency)
        coupon = self._get_best_coupon(origin_currency, destination_currency)
        rate = float(rate_data["rate"])
        quote = self._calculate_inverse(amount, rate, ranges, coupon) if mode == "receive" else self._calculate_direct(amount, rate, ranges, coupon)
        coupon_line = ""
        if quote.get("coupon_code"):
            coupon_line = (
                f" {copy['coupon_available']}: {quote['coupon_code']} "
                f"({self._fmt(quote.get('coupon_savings_amount', 0))} {origin_currency})."
            )
        quote.update({
            "origin_currency": origin_currency,
            "destination_currency": destination_currency,
            "mode": mode,
            "language": language,
            "tax_rate_id": rate_data["id"],
            "coupon_id": coupon["id"] if coupon else None,
            "summary_text": (
                f"{copy['quote_title']}: {copy['send_label']} {self._fmt(quote['amount_send'])} {origin_currency}, "
                f"{copy['rate_label']} {quote['rate']:.4f}, "
                f"{copy['commission_label']} {self._fmt(quote.get('commission_gross', quote['commission']))} {origin_currency}, "
                f"{copy['receive_label']} {self._fmt(quote['amount_receive'])} {destination_currency}."
                f"{coupon_line}"
            ),
        })
        return quote

    def build_whatsapp_quote_message(self, args=None):
        args = args or {}
        language = args.get("language", "es")
        copy = self._copy(language)
        origin_currency = self._normalize_currency(args.get("origin_currency"))
        destination_currency = self._normalize_currency(args.get("destination_currency"))
        amount_send = self._fmt(args.get("amount_send", 0))
        amount_receive = self._fmt(args.get("amount_receive", 0))
        commission = self._fmt(args.get("commission", 0))
        total_to_send = self._fmt(args.get("total_to_send", 0))
        coupon_code = args.get("coupon_code")
        coupon_discount = self._fmt(args.get("coupon_savings_amount", 0))
        rate = f"{float(args.get('rate', 0)):.4f}".rstrip("0").rstrip(".")

        prefixes = {
            "es": "Perfecto, los detalles de tu envío de Brasper hoy son los siguientes:",
            "pt": "Perfeito, os detalhes do seu envio Brasper hoje são os seguintes:",
            "en": "Great, here are the details of your Brasper transfer today:",
        }
        message = (
            f"{prefixes.get(language, prefixes['es'])}\n"
            f"*{copy['send_label']}:* {amount_send} {origin_currency}\n"
            f"{copy['rate_label']}: {rate}\n"
            f"*{copy['commission_label']}:* {commission} {origin_currency}\n"
            f"{copy['net_label']}: {total_to_send} {origin_currency}\n"
            f"*{copy['receive_label']}:* {amount_receive} {destination_currency}\n"
        )
        if coupon_code:
            message += (
                f"*{copy['coupon_label']}:* {coupon_code}\n"
                f"{copy['coupon_savings']}: {coupon_discount} {origin_currency}\n"
            )
        message += "\n" + copy["summary"].format(
            amount_send=amount_send,
            origin_currency=origin_currency,
            amount_receive=amount_receive,
            destination_currency=destination_currency,
        )
        wa_link = f"https://wa.me/{self.whatsapp_number}?text={quote(message)}"
        return {"message": message, "wa_link": wa_link, "language": language}

    def handoff_to_advisor(self, args=None):
        args = args or {}
        language = args.get("language", "es")
        summary = str(args.get("summary") or "").strip()
        copy_block = self._copy(language)
        advisor_copy = copy_block["advisor"]
        hint = copy_block.get("advisor_prefill_hint", "")
        # En el chat: instrucción, luego texto sugerido separado (evita mezclar con el enlace).
        # En WhatsApp al asesor: solo el resumen del cliente (wa_prefill).
        if summary and hint:
            message = f"{advisor_copy}\n\n{hint}\n\n{summary}"
        elif summary:
            message = f"{advisor_copy}\n\n{summary}"
        else:
            message = advisor_copy
        wa_prefill = summary if summary else advisor_copy
        wa_link = f"https://wa.me/{self.whatsapp_number}?text={quote(wa_prefill)}"
        return {
            "message": message,
            "wa_link": wa_link,
            "language": language,
            "advisor_phone": self.whatsapp_number,
        }
