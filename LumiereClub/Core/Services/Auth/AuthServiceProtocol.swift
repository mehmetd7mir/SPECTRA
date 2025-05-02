//
//  AuthServiceProtocol.swift
//  LumiereClub
//
//  Created by Mehmet  Demir on 2.05.2025.
//

protocol AuthServiceProtocol {
    func signIn(email: String, password: String, completion: @escaping (Result<Void, Error>) -> Void)
}
