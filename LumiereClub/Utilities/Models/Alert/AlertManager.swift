//
//  AlertManager.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 2.05.2025.
//
import UIKit

final class AlertManager {
    // Present alert using AlertModel
    static func showAlert(on viewController: UIViewController, with model: AlertModel) {
        let alert = UIAlertController(title: model.title, message: model.message, preferredStyle: .alert)

        for actionModel in model.actions {
            let style = mapStyle(actionModel.style)
            let alertAction = UIAlertAction(title: actionModel.title, style: style) { _ in
                actionModel.handler?()
            }
            alert.addAction(alertAction)
        }

        viewController.present(alert, animated: true)
    }

    // Map custom AlertActionStyle to UIKit UIAlertAction.Style
    private static func mapStyle(_ style: AlertActionStyle) -> UIAlertAction.Style {
        switch style {
        case .default:
            return .default
        case .cancel:
            return .cancel
        case .destructive:
            return .destructive
        }
    }
}
