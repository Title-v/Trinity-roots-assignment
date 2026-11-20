// UI-01 through UI-04. Assertions concern React state and requests, not persisted bookings.
const day = '2030-11-19'
const periods = (hours: number[]) => hours.map((hour) => ({
  starts_at: `${day}T${String(hour).padStart(2, '0')}:00:00+07:00`,
  ends_at: `${day}T${String(hour + 1).padStart(2, '0')}:00:00+07:00`,
}))
const account = { id: 1, email: 'ui-test@example.com' }
const rooms = [
  { id: 3, name: 'Oak Room', capacity: 10, image_key: 'rooms/oak.webp' },
  { id: 4, name: 'Fern Room', capacity: 8, image_key: 'rooms/fern.webp' },
]
const proposal = {
  candidate_id: 'original', resource_id: 3, room_name: 'Oak Room', capacity: 10,
  image_key: 'rooms/oak.webp', party_size: 5, slots: periods([14, 15]), equipment: [],
}
const message = 'Book Oak Room from 14:00 to 16:00 for 5 people, no equipment.'
const assistant = () => cy.get('.assistant-desktop')
const roomCard = () => cy.contains('li.booking-room-card', 'Oak Room')

function visitBooking() {
  // Freeze only Date, so the fixture date stays in the future without pausing UI timers.
  cy.clock(Date.UTC(2030, 10, 18), ['Date'])
  cy.visit('/booking')
  cy.wait('@account')
  assistant().should('be.visible')
}

function sendMessage() {
  assistant().find('input').type(message)
  assistant().contains('button', 'Send').click()
  cy.wait('@chat')
}

function useForm(hours: number[], equipment = false) {
  cy.get('input[name="day"]').type(day)
  cy.get('input[name="people"]').clear().type('5')
  cy.contains('button', 'Find rooms').click()
  cy.wait('@availability')
  for (const hour of hours) {
    const label = `${String(hour).padStart(2, '0')}:00–${String(hour + 1).padStart(2, '0')}:00`
    roomCard().contains('button', label).click()
  }
  cy.wait('@equipment')
  if (equipment) roomCard().contains('label', 'Projector').find('input').check()
  roomCard().contains('button', `Confirm booking · ${hours.length} hr`).click()
}

function arrangeConflict() {
  cy.intercept('POST', '/api/assistant/chat', { reply: 'Choose a room.', proposals: [proposal] }).as('chat')
  cy.intercept('POST', '/api/bookings/batch', { statusCode: 409, body: { detail: 'Room already taken.' } }).as('conflict')
  visitBooking()
  sendMessage()
}

function confirmIntoConflict() {
  assistant().find('input[type="radio"]').check()
  assistant().contains('button', 'Confirm booking').click()
  cy.wait('@conflict')
}

beforeEach(() => {
  // An unstubbed app request fails the test instead of reaching a real API or database.
  cy.intercept('/api/**', (request) => {
    throw new Error(`Unstubbed application request: ${request.method} ${request.url}`)
  })
  cy.intercept('GET', '/api/auth/me', account).as('account')
  cy.intercept('GET', '/api/rooms', rooms)
  const slots = periods(Array.from({ length: 10 }, (_, index) => index + 8)).map((slot) => ({ ...slot, status: 'available' }))
  cy.intercept('GET', '/api/rooms/slots*', { 3: slots, 4: slots }).as('availability')
  cy.intercept('POST', '/api/equipment/availability', [
    { name: 'Projector', quantity: 1 }, { name: 'Camera', quantity: 1 }, { name: 'Microphone', quantity: 1 },
  ]).as('equipment')
})

describe('Essential booking UI cases', () => {
  it('UI-01 maps form input into the request and renders confirmation and My bookings', () => {
    const chosen = periods([8, 10])
    cy.intercept('POST', '/api/bookings/batch', { statusCode: 201, body: { ids: [101] } }).as('create')
    cy.intercept('GET', '/api/bookings', [{
      id: 101, room_name: 'Oak Room', starts_at: chosen[0].starts_at, ends_at: chosen[1].ends_at,
      slots: chosen, status: 'confirmed', can_cancel: true,
      equipment: [{ id: 20, name: 'Projector 01', category: 'Projector' }],
    }]).as('myBookings')
    visitBooking()
    cy.contains('Booking confirmed').should('not.exist')
    useForm([8, 10], true)
    cy.wait('@create').its('request.body').should('deep.equal', {
      resource_id: 3, party_size: 5, slots: chosen, equipment: ['Projector'],
    })
    roomCard().should('contain.text', `Booking confirmed for Oak Room on ${day}: 2 hour(s).`)
    cy.contains('a', 'My bookings').click()
    cy.wait('@myBookings')
    cy.get('.my-booking-card').should('contain.text', 'Oak Room')
      .and('contain.text', '08:00–09:00').and('contain.text', '10:00–11:00')
      .and('contain.text', '19 November 2030').and('contain.text', 'Projector 01')
  })

  it('UI-02 requires selection and confirmation, then asks a preference after 409', () => {
    const alternate = cy.spy().as('alternativeRequests')
    cy.intercept('POST', '/api/assistant/alternatives', (request) => {
      alternate(request.body)
      request.reply({ reply: 'Choose another room.', proposals: [{ ...proposal, candidate_id: 'fern', resource_id: 4, room_name: 'Fern Room' }] })
    }).as('alternatives')
    arrangeConflict()
    assistant().contains('button', 'Confirm booking').should('be.disabled')
    cy.get('@conflict.all').should('have.length', 0)
    confirmIntoConflict()
    assistant().find('input[type="radio"]').should('not.exist')
    assistant().contains('button', 'Confirm booking').should('not.exist')
    for (const label of ['Same time', 'Same room', 'Either']) assistant().contains('button', label).should('be.enabled')
    cy.get('@alternativeRequests').should('not.have.been.called')
    assistant().contains('button', 'Same time').click()
    cy.wait('@alternatives').its('request.body').should('include', { resource_id: 3, party_size: 5, preference: 'same_time' })
    cy.get('@alternatives').its('request.body.slots').should('deep.equal', proposal.slots)
    assistant().contains('button', 'Confirm booking').should('be.disabled')
    cy.get('@conflict.all').should('have.length', 1)
  })

  it('UI-03 retains the draft after no matches and changes preference only on an explicit choice', () => {
    const requested = cy.spy().as('alternativeRequests')
    cy.intercept('POST', '/api/assistant/alternatives', (request) => {
      requested(request.body)
      if (request.body.preference === 'same_time') {
        request.reply({ reply: 'No other room is available for the original times.', proposals: [], alternative_request: { ...proposal, preference: null } })
      } else {
        expect(request.body.preference).to.equal('same_room')
        request.reply({ reply: 'Same room at another time.', proposals: [{ ...proposal, candidate_id: 'later', slots: periods([16, 17]), alternative_reason: 'same_room' }] })
      }
    }).as('alternatives')
    arrangeConflict()
    confirmIntoConflict()
    assistant().contains('button', 'Same time').click()
    cy.wait('@alternatives')
    assistant().should('contain.text', 'No other room is available for the original times.')
    assistant().find('input[type="radio"]').should('not.exist')
    assistant().contains('button', 'Confirm booking').should('not.exist')
    cy.get('@alternativeRequests').should('have.been.calledOnce')
    assistant().contains('button', 'Same room').click()
    cy.wait('@alternatives').its('request.body.slots').should('deep.equal', proposal.slots)
    cy.get('@alternatives').its('request.body.equipment').should('deep.equal', [])
    assistant().should('contain.text', '16:00–18:00').and('contain.text', '19 Nov 2030')
    assistant().contains('button', 'Confirm booking').should('be.disabled')
    cy.get('@alternativeRequests').should('have.been.calledTwice')
    cy.get('@conflict.all').should('have.length', 1)
  })

  it('UI-04 shows the chat error and leaves the normal form interactive', () => {
    const detail = 'The assistant is temporarily unavailable. Use the booking form to continue.'
    cy.intercept('POST', '/api/assistant/chat', { statusCode: 503, body: { detail } }).as('chat')
    cy.intercept('POST', '/api/bookings/batch', { statusCode: 201, body: { ids: [102] } }).as('create')
    visitBooking()
    sendMessage()
    assistant().find('[role="alert"]').should('have.text', detail)
    assistant().find('input').should('have.value', message).and('be.enabled')
    assistant().contains('button', 'Send').should('be.enabled')
    useForm([14])
    cy.wait('@create').its('request.body.slots').should('deep.equal', periods([14]))
    roomCard().should('contain.text', `Booking confirmed for Oak Room on ${day}: 1 hour(s).`)
    assistant().find('[role="alert"]').should('have.text', detail)
  })
})
