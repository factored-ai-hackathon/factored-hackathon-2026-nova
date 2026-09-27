export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  text: string
  /** i18n key of an error shown under the message */
  error?: 'errorGeneric' | 'errorNetwork'
  pending?: boolean
}
