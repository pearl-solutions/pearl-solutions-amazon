import time
from typing import Optional, Tuple

import requests


class AmazonSmsManagerPool:
    """Small wrapper around the SMSPool API (smspool.net).

    This class handles:
    - purchasing a phone number
    - polling for the SMS code associated with an order
    """

    BASE_URL = "https://api.smspool.net"

    def __init__(self, api_key: str) -> None:
        """Create a new SMSPool manager.

        Args:
            api_key: SMSPool API key used for Bearer authentication.
        """
        self.api_key = api_key

    def get_number(self) -> Optional[Tuple[str, str]]:
        """Purchase a phone number from SMSPool.

        Returns:
            A tuple of (phone_number, order_id) if the purchase succeeds,
            otherwise None.
        """
        # SMSPool expects multipart form fields; requests uses `files` for that.
        files = {
            "key": (None, self.api_key),
            "country": (None, "GB"),
            "service": (None, "39"),
            "pool": (None, ""),
            "max_price": (None, "0.20"),
            "pricing_option": (None, ""),
            "quantity": (None, "1"),
            "areacode": (None, ""),
            "exclude": (None, ""),
            "create_token": (None, ""),
        }

        try:
            response = requests.post(
                f"{self.BASE_URL}/purchase/sms",
                files=files,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException:
            # Network issue / non-2xx response: caller can retry.
            return None

        data = response.json()
        phone_number = data.get("phonenumber")
        order_id = data.get("order_id")
        if not phone_number or not order_id:
            # Defensive: API returned an unexpected payload.
            return None

        return phone_number, order_id

    def get_code_from_number(
        self,
        activation_id: str,
        interval: int = 5,
        timeout: int = 120,
    ) -> Optional[str]:
        """Poll SMSPool until an SMS code is received (or timeout is reached).

        Args:
            activation_id: SMSPool order id returned by :meth:`get_number`.
            interval: Time (in seconds) between polling attempts.
            timeout: Maximum waiting time (in seconds) before giving up.

        Returns:
            The SMS message/code as a string if received before timeout,
            otherwise None.
        """
        files = {
            "orderid": (None, activation_id),
            "key": (None, self.api_key),
        }

        start_time = time.time()

        print(f"[{activation_id}] Waiting for SMS...")

        while True:
            try:
                response = requests.post(
                    f"{self.BASE_URL}/sms/check",
                    files=files,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=20,
                )
                response.raise_for_status()
                data = response.json()
            except requests.RequestException:
                # Temporary network/API failure: stop cleanly, caller can retry.
                return None
            except ValueError:
                # Invalid JSON response.
                return None

            sms = data.get("sms")
            if sms:
                return str(sms)

            if time.time() - start_time > timeout:
                # No SMS received in time.
                return None

            time.sleep(interval)

class AmazonSmsManagerHero:
    """Small wrapper around the HeroSMS API.

    This class handles:
    - purchasing a phone number
    - polling for the SMS code associated with an order
    """

    BASE_URL = "https://hero-sms.com/stubs/handler_api.php"

    def __init__(self, api_key: str) -> None:
        """Create a new HeroSMS manager.

        Args:
            api_key: HeroSMS API key used for Bearer authentication.
        """
        self.api_key = api_key

    def get_number(self) -> Optional[Tuple[str, str]]:
        """Purchase a phone number from HeroSMS.

        Returns:
            A tuple of (phone_number, order_id) if the purchase succeeds,
            otherwise None.
        """
        # HeroSMS expects multipart form fields; requests uses `files` for that.

        params = {
            'action': 'getNumberV2',
            'service': 'am',
            'country': '16',
            'maxPrice': '0.11',
            'api_key': self.api_key
        }

        try:
            response = requests.get(
                f"{self.BASE_URL}",
                params=params,
                timeout=20,
            )
            response.raise_for_status()
        except requests.RequestException:
            # Network issue / non-2xx response: caller can retry.
            return None

        if "NO_NUMBERS" in response.text:
            print("No numbers available")
            return None

        data = response.json()
        phone_number = data.get("phoneNumber")[2:]
        order_id = data.get("activationId")
        if not phone_number or not order_id:
            # Defensive: API returned an unexpected payload.
            return None

        return phone_number, order_id

    def get_code_from_number(
        self,
        activation_id: str,
        interval: int = 5,
        timeout: int = 120,
    ) -> Optional[str]:
        """Poll HeroSMS until an SMS code is received (or timeout is reached).

        Args:
            activation_id: HeroSMS order id returned by :meth:`get_number`.
            interval: Time (in seconds) between polling attempts.
            timeout: Maximum waiting time (in seconds) before giving up.

        Returns:
            The SMS message/code as a string if received before timeout,
            otherwise None.
        """
        params = {
            'action': 'getStatusV2',
            'id': activation_id,
            'api_key': self.api_key
        }

        start_time = time.time()

        print(f"[{activation_id}] Waiting for SMS...")

        while True:
            try:
                response = requests.get(
                    f"{self.BASE_URL}",
                    params=params,
                    timeout=20,
                )
                response.raise_for_status()
                data = response.json()
                sms = data.get("sms")
                if sms:
                    return str(sms.get('code'))

                if time.time() - start_time > timeout:
                    # No SMS received in time.
                    return None
            except requests.RequestException:
                # Temporary network/API failure: stop cleanly, caller can retry.
                return None
            except ValueError:
                # Invalid JSON response.
                return None

            time.sleep(interval)