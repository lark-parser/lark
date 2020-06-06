# -*- coding: utf-8 -*-
from . import core as html5
from . import utils

class Button(html5.Button):

	def __init__(self, txt=None, callback=None, className=None, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self["class"] = "btn"

		if className:
			self.addClass(className)

		self["type"] = "button"

		if txt is not None:
			self.setText(txt)

		self.callback = callback
		self.sinkEvent("onClick")

	def setText(self, txt):
		if txt is not None:
			self.element.innerHTML = txt
			self["title"] = txt
		else:
			self.element.innerHTML = ""
			self["title"] = ""

	def onClick(self, event):
		event.stopPropagation()
		event.preventDefault()
		if self.callback is not None:
			self.callback(self)


class Input(html5.Input):
	def __init__(self, type="text", placeholder=None, callback=None, id=None, focusCallback=None, *args, **kwargs):
		"""

		:param type: Input type. Default: "text
		:param placeholder: Placeholder text. Default: None
		:param callback: Function to be called onChanged: callback(id, value)
		:param id: Optional id of the input element. Will be passed to callback
		:return:
		"""
		super().__init__(*args, **kwargs)
		self["class"] = "input"
		self["type"] = type
		if placeholder is not None:
			self["placeholder"] = placeholder

		self.callback = callback
		if id is not None:
			self["id"] = id
		self.sinkEvent("onChange")

		self.focusCallback = focusCallback
		if focusCallback:
			self.sinkEvent("onFocus")

	def onChange(self, event):
		event.stopPropagation()
		event.preventDefault()
		if self.callback is not None:
			self.callback(self, self["id"], self["value"])

	def onFocus(self, event):
		event.stopPropagation()
		event.preventDefault()
		if self.focusCallback is not None:
			self.focusCallback(self, self["id"], self["value"])

	def onDetach(self):
		super().onDetach()
		self.callback = None


class Popup(html5.Div):
	def __init__(self, title=None, id=None, className=None, icon=None, enableShortcuts=True, closeable=True, *args, **kwargs):
		super().__init__("""
			<div class="box" [name]="popupBox">
				<div class="box-head" [name]="popupHead">
					<div class="item" [name]="popupHeadItem">
						<div class="item-image">
							<i class="i i--small" [name]="popupIcon"></i>
						</div>
						<div class="item-content">
							<div class="item-headline" [name]="popupHeadline"></div>
						</div>
					</div>
				</div>
				<div class="box-body box--content" [name]="popupBody"></div>
				<div class="box-foot box--content bar" [name]="popupFoot"></div>
			</div>
		""")

		self.appendChild = self.popupBody.appendChild
		self.fromHTML = lambda *args, **kwargs: self.popupBody.fromHTML(*args, **kwargs) if kwargs.get("bindTo") else self.popupBody.fromHTML(bindTo=self, *args, **kwargs)

		self["class"] = "popup popup--center is-active"
		if className:
			self.addClass(className)

		if closeable:
			closeBtn = Button("&times;", self.close, className="item-action")
			closeBtn.removeClass("btn")
			self.popupHeadItem.appendChild(closeBtn)

		if title:
			self.popupHeadline.appendChild(title)

		if icon:
			self.popupIcon.appendChild(icon[0])
		elif title:
			self.popupIcon.appendChild(title[0])
		else:
			self.popupIcon.appendChild("Vi") #fixme!!! this _LIBRARY_ is not only used in the Vi...

		# id can be used to pass information to callbacks
		self.id = id

		#FIXME: Implement a global overlay! One popupOverlay next to a list of popups.
		self.popupOverlay = html5.Div()
		self.popupOverlay["class"] = "popup-overlay is-active"

		self.enableShortcuts = enableShortcuts
		self.onDocumentKeyDownMethod = None

		self.popupOverlay.appendChild(self)
		html5.Body().appendChild(self.popupOverlay)

		#FIXME: Close/Cancel every popup with click on popupCloseBtn without removing the global overlay.

	def onAttach(self):
		super(Popup, self).onAttach()

		if self.enableShortcuts:
			self.onDocumentKeyDownMethod = self.onDocumentKeyDown  # safe reference to method
			html5.document.addEventListener("keydown", self.onDocumentKeyDownMethod)

	def onDetach(self):
		super(Popup, self).onDetach()

		if self.enableShortcuts:
			html5.document.removeEventListener("keydown", self.onDocumentKeyDownMethod)

	def onDocumentKeyDown(self, event):
		if html5.isEscape(event):
			self.close()

	def close(self, *args, **kwargs):
		html5.Body().removeChild(self.popupOverlay)
		self.popupOverlay = None



class InputDialog(Popup):
	def __init__(self, text, value="", successHandler=None, abortHandler=None,
				 	successLbl="OK", abortLbl="Cancel", placeholder="", *args, **kwargs):

		super().__init__(*args, **kwargs)
		self.addClass("popup--inputdialog")

		self.sinkEvent("onKeyDown", "onKeyUp")

		self.successHandler = successHandler
		self.abortHandler = abortHandler

		self.fromHTML(
			"""
			<div class="input-group">
				<label class="label">
					{{text}}
				</label>
				<input class="input" [name]="inputElem" value="{{value}}" placeholder="{{placeholder}}" />
			</div>
			""",
			vars={
				"text": text,
				"value": value,
				"placeholder": placeholder
			}
		)

		# Cancel
		self.popupFoot.appendChild(Button(abortLbl, self.onCancel, className="btn--cancel btn--danger"))

		# Okay
		self.okayBtn = Button(successLbl, self.onOkay, className="btn--okay btn--primary")
		if not value:
			self.okayBtn.disable()

		self.popupFoot.appendChild(self.okayBtn)

		self.inputElem.focus()

	def onKeyDown(self, event):
		if html5.isReturn(event) and self.inputElem["value"]:
			event.stopPropagation()
			event.preventDefault()
			self.onOkay()

	def onKeyUp(self, event):
		if self.inputElem["value"]:
			self.okayBtn.enable()
		else:
			self.okayBtn.disable()

	def onDocumentKeyDown(self, event):
		if html5.isEscape(event):
			event.stopPropagation()
			event.preventDefault()
			self.onCancel()

	def onOkay(self, *args, **kwargs):
		if self.successHandler:
			self.successHandler(self, self.inputElem["value"])
		self.close()

	def onCancel(self, *args, **kwargs):
		if self.abortHandler:
			self.abortHandler(self, self.inputElem["value"])
		self.close()


class Alert(Popup):
	"""
	Just displaying an alerting message box with OK-button.
	"""

	def __init__(self, msg, title=None, className=None, okCallback=None, okLabel="OK", icon="!", closeable=True, *args, **kwargs):
		super().__init__(title, className=None, icon=icon, closeable=closeable, *args, **kwargs)
		self.addClass("popup--alert")

		if className:
			self.addClass(className)

		self.okCallback = okCallback

		message = html5.Span()
		message.addClass("alert-msg")
		self.popupBody.appendChild(message)

		if isinstance(msg, str):
			msg = msg.replace("\n", "<br>")

		message.appendChild(msg, bindTo=False)

		self.sinkEvent("onKeyDown")

		if closeable:
			okBtn = Button(okLabel, callback=self.onOkBtnClick)
			okBtn.addClass("btn--okay btn--primary")
			self.popupFoot.appendChild(okBtn)

			okBtn.focus()

	def drop(self):
		self.okCallback = None
		self.close()

	def onOkBtnClick(self, sender=None):
		if self.okCallback:
			self.okCallback(self)

		self.drop()

	def onKeyDown(self, event):
		if html5.isReturn(event):
			event.stopPropagation()
			event.preventDefault()
			self.onOkBtnClick()


class YesNoDialog(Popup):
	def __init__(self, question, title=None, yesCallback=None, noCallback=None,
	                yesLabel="Yes", noLabel="No", icon="?",
	                    closeable=False, *args, **kwargs):
		super().__init__(title, closeable=closeable, icon=icon, *args, **kwargs)
		self.addClass("popup--yesnodialog")

		self.yesCallback = yesCallback
		self.noCallback = noCallback

		lbl = html5.Span()
		lbl["class"].append("question")
		self.popupBody.appendChild(lbl)

		if isinstance(question, html5.Widget):
			lbl.appendChild(question)
		else:
			utils.textToHtml(lbl, question)

		if len(noLabel):
			btnNo = Button(noLabel, className="btn--no", callback=self.onNoClicked)
			#btnNo["class"].append("btn--no")
			self.popupFoot.appendChild(btnNo)

		btnYes = Button(yesLabel, callback=self.onYesClicked)
		btnYes["class"].append("btn--yes")
		self.popupFoot.appendChild(btnYes)

		self.sinkEvent("onKeyDown")
		btnYes.focus()

	def onKeyDown(self, event):
		if html5.isReturn(event):
			event.stopPropagation()
			event.preventDefault()
			self.onYesClicked()

	def onDocumentKeyDown(self, event):
		if html5.isEscape(event):
			event.stopPropagation()
			event.preventDefault()
			self.onNoClicked()

	def drop(self):
		self.yesCallback = None
		self.noCallback = None
		self.close()

	def onYesClicked(self, *args, **kwargs):
		if self.yesCallback:
			self.yesCallback(self)

		self.drop()

	def onNoClicked(self, *args, **kwargs):
		if self.noCallback:
			self.noCallback(self)

		self.drop()


class SelectDialog(Popup):

	def __init__(self, prompt, items=None, title=None, okBtn="OK", cancelBtn="Cancel", forceSelect=False,
	             callback=None, *args, **kwargs):
		super().__init__(title, *args, **kwargs)
		self["class"].append("popup--selectdialog")

		self.callback = callback
		self.items = items
		assert isinstance(self.items, list)

		# Prompt
		if prompt:
			lbl = html5.Span()
			lbl["class"].append("prompt")

			if isinstance(prompt, html5.Widget):
				lbl.appendChild(prompt)
			else:
				utils.textToHtml(lbl, prompt)

			self.popupBody.appendChild(lbl)

		# Items
		if not forceSelect and len(items) <= 3:
			for idx, item in enumerate(items):
				if isinstance(item, dict):
					title = item.get("title")
					cssc = item.get("class")
				elif isinstance(item, tuple):
					title = item[1]
					cssc = None
				else:
					title = item

				btn = Button(title, callback=self.onAnyBtnClick)
				btn.idx = idx

				if cssc:
					btn.addClass(cssc)

				self.popupBody.appendChild(btn)
		else:
			self.select = html5.Select()
			self.popupBody.appendChild(self.select)

			for idx, item in enumerate(items):
				if isinstance(item, dict):
					title = item.get("title")
				elif isinstance(item, tuple):
					title = item[1]
				else:
					title = item

				opt = html5.Option(title)
				opt["value"] = str(idx)

				self.select.appendChild(opt)

			if okBtn:
				self.popupFoot.appendChild(Button(okBtn, callback=self.onOkClick))

			if cancelBtn:
				self.popupFoot.appendChild(Button(cancelBtn, callback=self.onCancelClick))

	def onAnyBtnClick(self, sender):
		item = self.items[sender.idx]

		if isinstance(item, dict) and item.get("callback") and callable(item["callback"]):
			item["callback"](item)

		if self.callback:
			self.callback(item)

		self.items = None
		self.close()

	def onCancelClick(self, sender=None):
		self.close()

	def onOkClick(self, sender=None):
		assert self.select["selectedIndex"] >= 0
		item = self.items[int(self.select.children(self.select["selectedIndex"])["value"])]

		if isinstance(item, dict) and item.get("callback") and callable(item["callback"]):
			item["callback"](item)

		if self.callback:
			self.callback(item)

		self.items = None
		self.select = None
		self.close()


class TextareaDialog(Popup):
	def __init__(self, text, value="", successHandler=None, abortHandler=None, successLbl="OK", abortLbl="Cancel",
	             *args, **kwargs):
		super().__init__(*args, **kwargs)
		self["class"].append("popup--textareadialog")

		self.successHandler = successHandler
		self.abortHandler = abortHandler

		span = html5.Span()
		span.element.innerHTML = text
		self.popupBody.appendChild(span)

		self.inputElem = html5.Textarea()
		self.inputElem["value"] = value
		self.popupBody.appendChild(self.inputElem)

		okayBtn = Button(successLbl, self.onOkay)
		okayBtn["class"].append("btn--okay")
		self.popupFoot.appendChild(okayBtn)

		cancelBtn = Button(abortLbl, self.onCancel)
		cancelBtn["class"].append("btn--cancel")
		self.popupFoot.appendChild(cancelBtn)

		self.sinkEvent("onKeyDown")

		self.inputElem.focus()

	def onDocumentKeyDown(self, event):
		if html5.isEscape(event):
			event.stopPropagation()
			event.preventDefault()
			self.onCancel()

	def onOkay(self, *args, **kwargs):
		if self.successHandler:
			self.successHandler(self, self.inputElem["value"])
		self.close()

	def onCancel(self, *args, **kwargs):
		if self.abortHandler:
			self.abortHandler(self, self.inputElem["value"])
		self.close()
