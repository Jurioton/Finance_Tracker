// Change the currency here if you want (e.g. 'USD', 'EUR').
const CURRENCY = 'INR'
const LOCALE = 'en-IN'

const money = new Intl.NumberFormat(LOCALE, { style: 'currency', currency: CURRENCY, maximumFractionDigits: 2 })

export const formatMoney = (value) => money.format(value || 0)

export const currentMonth = () => new Date().toISOString().slice(0, 7) // "YYYY-MM"

export const today = () => new Date().toISOString().slice(0, 10) // "YYYY-MM-DD"

export const monthLabel = (month) => {
  const [y, m] = month.split('-').map(Number)
  return new Date(y, m - 1, 1).toLocaleDateString(LOCALE, { month: 'short', year: 'numeric' })
}

export const formatDate = (iso) =>
  new Date(iso + 'T00:00:00').toLocaleDateString(LOCALE, { day: 'numeric', month: 'short', year: 'numeric' })
