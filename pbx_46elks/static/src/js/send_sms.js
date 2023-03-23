function send_sms(){
    to_number = $("#sms_to")[0].value
    sms_message = $("#sms_message")[0].value

    $.post({
		url: "/46elks/sms/send/",
		method: "POST",
		data:{
			to: to_number,
			message: sms_message,
		}
	});
}