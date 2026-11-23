import { describe, expect, it } from 'vitest'
import { cleanEmail, decodeEntities, emailBody, emailHeadline } from './email-text'
import { dueLabel, relativeDay } from './time'

describe('email text', () => {
  it('decodes named and numeric entities', () => {
    expect(decodeEntities('Dear&nbsp;Dhanush &amp; team &#39;hi&#39; &#x41;')).toBe("Dear Dhanush & team 'hi' A")
  })

  it('drops URLs, placeholders, separator lines and the footer', () => {
    const raw =
      'Your application was viewed by Netcomm\n---------------------------------------- This email was intended for Dhanush (SDE I) Learn why we included this: https://www.linkedin.com/help/x?a=1'
    expect(cleanEmail(raw)).toBe('Your application was viewed by Netcomm')
    expect(cleanEmail('Apply for [[RECRUITING_JOB_TITLE]] 139822 at https://x.example/a')).toBe('Apply for 139822 at')
  })

  it('splits the subject line from the body', () => {
    const raw = 'Update on your application\nDear&nbsp;Dhanush,\nThank you for applying.'
    expect(emailHeadline(raw)).toBe('Update on your application')
    expect(emailBody(raw)).toBe('Dear Dhanush, Thank you for applying.')
    expect(emailHeadline(null)).toBe('')
  })
})

describe('time phrases', () => {
  const now = new Date('2026-11-23T10:00:00')
  it('names nearby days', () => {
    expect(relativeDay('2026-11-23T01:00:00', now)).toBe('today')
    expect(relativeDay('2026-11-22T23:00:00', now)).toBe('yesterday')
    expect(relativeDay('2026-11-13T10:00:00', now)).toBe('10 days ago')
    expect(relativeDay('2026-11-26T10:00:00', now)).toBe('in 3 days')
  })

  it('says how overdue something is', () => {
    expect(dueLabel('2026-11-20T10:00:00', now)).toEqual({ text: 'Overdue by 3 days', overdue: true })
    expect(dueLabel('2026-11-22T10:00:00', now)).toEqual({ text: 'Overdue by 1 day', overdue: true })
    expect(dueLabel('2026-11-23T18:00:00', now)).toEqual({ text: 'Due today', overdue: false })
    expect(dueLabel('2026-11-24T09:00:00', now)).toEqual({ text: 'Due tomorrow', overdue: false })
  })
})
