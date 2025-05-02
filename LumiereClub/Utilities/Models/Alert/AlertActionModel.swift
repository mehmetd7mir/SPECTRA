//
//  AlertActionModel.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 2.05.2025.
//
import Foundation

struct AlertActionModel {
    let title: String
    let style: AlertActionStyle
    let handler: (() -> Void)?
}

extension AlertActionModel {
    static let ok = AlertActionModel(
        title: LocalizedKey.ok.localized,
        style: .default,
        handler: nil
    )
}
