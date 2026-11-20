# User guide

[Back to README](../README.md)

## Booking form

1. Click **Book now** and enter a date and group size. The page shows rooms that fit your group and refreshes availability about every five seconds.
2. Pick one or more one-hour slots in the same room on the same day. Optionally tick **Projector**, **Camera**, or **Microphone** to reserve one unit of each selected type for all those slots, then confirm. The checkboxes show how many units are available for the whole selection. Rooms can be booked daily from **08:00 to 18:00 Bangkok time**. Each slot must start in the future and on the hour.
3. Open **My bookings** to see your reservations and assigned equipment. All selected slots appear in one booking. Use **Edit booking** to change the date, time slots, or equipment, then **Save changes**. Cancellation releases the room and all its equipment together.

## AI booking

The assistant is on the booking page. On mobile, tap **Ask AI**. Try **“Book a room for 8 with a projector tomorrow from 10:00 to 12:00”** or **“จองห้องสำหรับ 8 คน พร้อมโปรเจคเตอร์ พรุ่งนี้ 10:00–12:00”**. The backend checks the full time period and requested equipment, then shows matching rooms with photos and capacities. Select a room, review its date, time, and equipment, then click **Confirm booking**. The slots and equipment are reserved when confirmation succeeds, after another availability check.

For a new booking, the assistant asks for a missing start or end time before showing rooms. An explicit duration, such as two hours, lets it calculate the end time from the stated start. Matching rooms are ordered by capacity, starting with the smallest that fits the group. A request for a large room puts the largest choices first. The user selects the room before confirming.

Before preparing a new booking, the chat asks whether equipment is needed if the user has not stated a preference. Reply with the equipment names or say **“ไม่ต้องการ”** / **“no equipment”**. The assistant keeps the date, time, and group size from the conversation. An equipment choice or an explicit decline in the initial request lets the chat proceed directly to room selection.

The equipment answer applies to the current booking. After confirmation or discarding a draft, the next request starts with fresh context, while previous messages remain visible in the chat.

## Manage bookings through chat

To manage an existing booking, try **“Show my bookings”**, **“เลื่อนการจองของฉันเป็นพรุ่งนี้ 13:00–15:00 แล้วเพิ่มกล้อง”**, or **“Cancel my booking”**. The chat shows your own matching reservations. Select one, review or adjust the proposed date, time slots, and equipment, then click **Confirm changes** or **Confirm cancellation**. These buttons use the same booking APIs as **My bookings**. Changes are saved after confirmation.

If you give only a new start time, the edit form shifts the existing slots together, preserving their duration and gaps. You can adjust the proposed slots before confirming. Adding or removing equipment keeps the other selected types.

## Conflict suggestions

This feature helps when a requested room or equipment is unavailable, including when someone else books it while you are reviewing a chat proposal. It applies to new chat bookings. A conflicting edit keeps the original reservation and requires a new selection.

For example, you request **Oak Room, 14:00–16:00, for 5 people**. Someone else confirms that room before you do. Your confirmation returns **409 Conflict**, so your booking is not created. The chat keeps your requested details and asks what you want to keep:

| Choice | What may change | What stays fixed |
| --- | --- | --- |
| **Same time** | The room | Every selected time slot |
| **Same room** | The time | The selected room |
| **Either** | The room and time | The date, group size, equipment, and total duration |

The date, group size, equipment, and total duration stay fixed for all three choices. “Same room” is available only when a room has been named or selected.

You can press a button or give a short answer such as “same time”, “same room”, or “either”, also supported in Thai. Ambiguous answers ask you to use the buttons. To change the date or other requirements, choose **New search**.

If you choose **Same time**, the chat might offer Lotus Room from 14:00–16:00. If you choose **Same room**, it might offer Oak Room from 12:00–14:00 or 16:00–18:00. These are examples, not guaranteed availability.

Each option shows a room photo, capacity, date, and time. You must select an option and press **Confirm booking** again. Choosing a preference does not create a booking.
