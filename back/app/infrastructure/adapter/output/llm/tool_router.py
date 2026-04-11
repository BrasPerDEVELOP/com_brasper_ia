class ToolRouter():
    def __init__(self, calendar_use_case, crm_use_case, brasper_use_case):
        self.calendar_use_case = calendar_use_case
        self.crm_use_case = crm_use_case
        self.brasper_use_case = brasper_use_case

    def router(self,tool_call):
        name=tool_call["name"]
        args=tool_call.get("args")

        #si viene como string
        if isinstance(args,str):
            import json
            args=json.loads(args)

        if name=="create_calendar_event":
            return self.calendar_use_case.execute(args)

        if name=="save_lead":
            return self.crm_use_case.save_lead_with_cache(args)

        if name=="get_supported_currencies":
            return self.brasper_use_case.get_supported_currencies(args)

        if name=="get_exchange_rates":
            return self.brasper_use_case.get_exchange_rates(args)

        if name=="get_commission_ranges":
            return self.brasper_use_case.get_commission_ranges(args)

        if name=="get_active_coupons":
            return self.brasper_use_case.get_active_coupons(args)

        if name=="quote_exchange_operation":
            return self.brasper_use_case.quote_exchange_operation(args)

        if name=="build_whatsapp_quote_message":
            return self.brasper_use_case.build_whatsapp_quote_message(args)

        if name=="handoff_to_advisor":
            return self.brasper_use_case.handoff_to_advisor(args)

        return ValueError(f"Tool no soportada {name}")
