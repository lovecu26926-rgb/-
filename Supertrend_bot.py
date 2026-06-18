    # 🎯 테스트용: 종목 없어도 무조건 알림 보내는 로직
    if not buy_alerts:
        send_telegram(f"📊 <b>[테스트 알림]</b> 오늘 매수 전환 종목 없음 (봇 정상 작동 확인)")
        return
