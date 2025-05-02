//
//  AlertModel.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 2.05.2025.
//
import Foundation
import Foundation

struct AlertModel {
    let title: String
    let message: String
    let actions: [AlertActionModel]

    init(title: String, message: String, actions: [AlertActionModel] = [.ok]) {
        self.title = title
        self.message = message
        self.actions = actions
    }
}
