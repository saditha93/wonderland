# Wonderland: a five-minute MVP demo

## 1. Start

Run `./start.sh` from the project folder. Keep that terminal open. It shows the two URLs and your private visitor/admin passwords. You do not need to run other services manually.

If an older app is still running, close its API/frontend terminals first. Do not run two copies.

## 2. Visitor: book and pay

1. Open http://localhost:5173 and browse **Explore**.
2. Select **Sign in**. Use `visitor@wonderland.local` and its password shown in the terminal.
3. Open **Book a visit**. Select **Family**, **4 guests**, **today's date** and a time slot.
4. Create the booking, then select **Continue to payment**. The demo confirms payment and opens the QR ticket; no card or real money is involved.
5. Copy the **WL- booking reference** shown on the ticket. You do not need to copy tokens or QR scan data.
6. Open **My bookings** to show the confirmed booking.

The launcher enables local demo mode: today's booking is allowed even after a slot has passed. It does not allow past visit dates. This exception is unavailable in cloud mode.

## 3. Admin: check in and record a ride

1. Open http://localhost:5174. Sign in with `admin@wonderland.local` and its private password from the terminal.
2. Open **Check-in**, paste the WL- reference and select **Check ticket**.
3. Confirm **4 guests**, then select **Register arrival**. Show the new arrival below.
4. Check the same reference again to show that duplicate admission is blocked.
5. Open **Rides**. Choose the checked-in booking from the dropdown, choose an open attraction, enter **2** riders and record the ride.

A ticket must be paid and valid today. Ride recording requires today's check-in. These checks still run on the backend.

## 4. Show the results

Open admin **Reports** and select **Refresh reports**. Allow a few seconds for processing. Show:

- Daily visitor arrivals.
- Tickets sold by tier.
- Revenue by tier.
- Popular attractions.
- Busiest and quietest opening hours.

Hourly reports cover 09:00–18:00 in Sri Lanka. An evening/night demo can correctly show zero arrivals in those hours; outside-hours arrivals remain in daily totals.

For additional assignment features, show **Attractions** and **Tickets & prices** in admin. Visitor **My account** contains the profile and visit history. These do not need to interrupt the main demo.

## 5. Stop / test

Press **Ctrl-C** in the startup terminal to stop the apps. Saved records remain. The local database stays available for the next run; advanced database shutdown is optional.

Run `./start.sh test` to check the Python tests and both production builds. This can run without starting the app screens.

Refresh clears the in-memory session: sign in again. Passwords are also available in private `secrets/local.accounts.json`; do not include them in screenshots or reports. If startup fails, its three component logs are in `tmp/mvp/`.
